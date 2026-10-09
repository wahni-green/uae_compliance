import frappe

from uae_compliance.tests import create_submitted_purchase_invoice
from uae_compliance.uae_compliance.doctype.uae_vat_return.test_uae_vat_return import (
	VATReturnTestCase,
	_boxes,
)
from uae_compliance.uae_compliance.utils.vat_return.apportionment import (
	get_annual_apportionment,
	get_recovery_ratio,
)


class TestRecoveryRatio(VATReturnTestCase):
	def test_ratio_is_taxable_over_all_supplies_rounded(self):
		self.assertEqual(get_recovery_ratio(600, 400), 60)
		self.assertEqual(get_recovery_ratio(2, 1), 67)  # 66.67
		self.assertEqual(get_recovery_ratio(1, 2), 33)  # 33.33
		self.assertEqual(get_recovery_ratio(1, 199), 1)  # 0.5 rounds up

	def test_no_supplies_recovers_everything(self):
		self.assertEqual(get_recovery_ratio(0, 0), 100)

	def test_only_exempt_supplies_recover_nothing(self):
		self.assertEqual(get_recovery_ratio(0, 500), 0)


class TestPartialExemptionInTheReturn(VATReturnTestCase):
	def _purchase(self, attribution, rate=1000):
		return create_submitted_purchase_invoice(
			[{"rate": rate, "uae_input_tax_attribution": attribution}],
			taxes=[(self.input, 5, "Add")],
			posting_date=self.date,
		)

	def _generate(self):
		doc = self.new_return()
		doc.generate_return()
		return doc

	def test_residual_input_vat_is_recovered_at_the_ratio(self):
		self.sale(rate=600, emirate="Dubai")  # taxable
		self.sale(item="_Test Exempt Item", rate=400, vat_rate=0)  # exempt -> 60%
		self._purchase("Residual")  # VAT 50

		doc = self._generate()
		box = _boxes(doc)["9"]

		self.assertEqual(doc.recovery_ratio, 60)
		self.assertEqual(box.amount, 1000)
		self.assertEqual(box.vat_amount, 30)
		self.assertEqual((doc.residual_input_vat, doc.residual_recoverable_vat), (50, 30))
		self.assertEqual((doc.taxable_supplies_value, doc.exempt_supplies_value), (600, 400))

	def test_taxable_attribution_is_fully_recoverable(self):
		self.sale(item="_Test Exempt Item", rate=400, vat_rate=0)
		self._purchase("Taxable Supplies")

		self.assertEqual(_boxes(self._generate())["9"].vat_amount, 50)

	def test_blank_attribution_is_fully_recoverable(self):
		self.sale(item="_Test Exempt Item", rate=400, vat_rate=0)
		self._purchase("")

		self.assertEqual(_boxes(self._generate())["9"].vat_amount, 50)

	def test_exempt_attribution_claims_nothing(self):
		self._purchase("Exempt Supplies")

		box = _boxes(self._generate())["9"]
		self.assertEqual((box.amount, box.vat_amount), (0, 0))

	def test_no_exempt_supplies_means_full_recovery(self):
		self.sale(rate=600)
		self._purchase("Residual")

		doc = self._generate()
		self.assertEqual(doc.recovery_ratio, 100)
		self.assertEqual(_boxes(doc)["9"].vat_amount, 50)


class TestAnnualApportionment(VATReturnTestCase):
	def _filed_return(self, taxable, exempt, residual_purchase):
		self.date = frappe.utils.add_days(self.date, 0)
		self.sale(rate=taxable)
		self.sale(item="_Test Exempt Item", rate=exempt, vat_rate=0)
		create_submitted_purchase_invoice(
			[{"rate": residual_purchase, "uae_input_tax_attribution": "Residual"}],
			taxes=[(self.input, 5, "Add")],
			posting_date=self.date,
		)
		doc = self.new_return()
		doc.generate_return()
		doc.mark_as_filed()
		return doc

	def test_true_up_uses_the_annual_ratio(self):
		from uae_compliance.tests import get_unique_test_date

		# Period 1: taxable 500, exempt 500 -> 50%; residual VAT 100 recovers 50.
		first = self._filed_return(500, 500, 2000)
		start = first.from_date
		# Period 2: taxable 1000, exempt 500 -> 67%; residual VAT 100 recovers 67.
		self.date = get_unique_test_date()
		second = self._filed_return(1000, 500, 2000)
		end = second.to_date
		self.assertEqual((first.recovery_ratio, second.recovery_ratio), (50, 67))

		result = get_annual_apportionment(self.company, start, end)

		# Year: taxable 1500, exempt 1000 -> 60%. Residual VAT 200 -> 120 recoverable, 117 claimed.
		self.assertEqual(result["returns"], 2)
		self.assertEqual(result["annual_ratio"], 60)
		self.assertEqual(result["residual_input_vat"], 200)
		self.assertEqual(result["annual_recoverable"], 120)
		self.assertEqual(result["claimed"], 117)
		self.assertEqual(result["adjustment"], 3)

	def test_true_up_picks_up_the_shortfall(self):
		from uae_compliance.tests import get_unique_test_date

		first = self._filed_return(100, 900, 2000)  # ratio 10%: residual 100, recovers 10
		start = first.from_date
		self.date = get_unique_test_date()
		second = self._filed_return(900, 100, 2000)  # ratio 90%: residual 100, recovers 90
		end = second.to_date

		result = get_annual_apportionment(self.company, start, end)

		# Annual: taxable 1000, exempt 1000 -> 50%. 200 x 50% = 100 recoverable; claimed 100.
		self.assertEqual(result["annual_ratio"], 50)
		self.assertEqual(result["adjustment"], 0)

		# A year with unequal residual VAT does produce an adjustment.
		frappe.db.set_value("UAE VAT Return", second.name, "residual_input_vat", 300)
		again = get_annual_apportionment(self.company, start, end)
		self.assertEqual(again["adjustment"], flt_(0.5 * 400 - 100))

	def test_requires_filed_returns(self):
		self.new_return()
		self.assertRaises(
			frappe.ValidationError,
			get_annual_apportionment,
			self.company,
			self.date,
			self.date,
		)

	def test_adjustment_doctype_calculates_from_filed_returns(self):
		first = self._filed_return(100, 900, 2000)
		adjustment = frappe.get_doc(
			{
				"doctype": "UAE VAT Adjustment",
				"company": self.company,
				"adjustment_type": "Annual Apportionment",
				"posting_date": first.to_date,
				"period_from": first.from_date,
				"period_to": first.to_date,
				"vat_amount": 1,
			}
		)
		adjustment.calculate_apportionment()

		# One period only: annual ratio 10%, 10 recoverable, 10 claimed.
		self.assertEqual(adjustment.vat_amount, 0)
		self.assertIn("10%", adjustment.remarks)


def flt_(value):
	return frappe.utils.flt(value, 2)
