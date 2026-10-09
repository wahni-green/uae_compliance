import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import (
	configure_vat_settings,
	create_submitted_purchase_invoice,
	create_submitted_sales_invoice,
	get_uae_test_company,
	get_unique_test_date,
	make_customer,
	make_item,
)


def _boxes(doc) -> dict:
	return {row.box_code: row for row in doc.boxes}


class VATReturnTestCase(FrappeTestCase):
	def setUp(self):
		self.company = get_uae_test_company()
		self.output, self.input = configure_vat_settings(self.company)
		self.date = get_unique_test_date()
		make_customer("_Test UAE Customer")
		make_item("_Test Zero Item", "Zero Rated")
		make_item("_Test Exempt Item", "Exempt")

	def sale(self, item="_Test Print Item", rate=1000, emirate="Dubai", vat_rate=None, qty=1, **kwargs):
		row = {"item_code": item, "rate": rate, "qty": qty}
		if vat_rate is not None:
			row["vat_rate"] = vat_rate

		return create_submitted_sales_invoice(
			[row], emirate=emirate, posting_date=self.date, customer="_Test UAE Customer", **kwargs
		)

	def new_return(self):
		return frappe.get_doc(
			{
				"doctype": "UAE VAT Return",
				"company": self.company,
				"from_date": self.date,
				"to_date": self.date,
			}
		).insert()


class TestVATReturnGeneration(VATReturnTestCase):
	def _create_period_transactions(self):
		dubai = self.sale(rate=100, qty=10, emirate="Dubai")
		self.sale(rate=200, emirate="Sharjah")
		self.sale(item="_Test Zero Item", rate=300, vat_rate=0)
		self.sale(item="_Test Exempt Item", rate=400, vat_rate=0)

		# A credit note for one of the ten units (100) nets into box 1b.
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		credit_note = make_return_doc("Sales Invoice", dubai.name)
		credit_note.posting_date = self.date
		credit_note.set_posting_time = 1
		credit_note.uae_emirate = "Dubai"
		credit_note.uae_credit_note_reason = "Returned"
		credit_note.items[0].qty = -1
		credit_note.insert()
		credit_note.submit()

		# Ordinary standard rated purchase: box 9.
		create_submitted_purchase_invoice(
			[{"rate": 500}], taxes=[(self.input, 5, "Add")], posting_date=self.date
		)
		# Reverse charge services: boxes 3 and 10.
		create_submitted_purchase_invoice(
			[{"rate": 100}],
			taxes=[(self.output, 5, "Deduct"), (self.input, 5, "Add")],
			posting_date=self.date,
			uae_is_reverse_charge=1,
			uae_reverse_charge_type="Import of Services",
		)
		# Import of goods with postponed VAT: boxes 6 and 10.
		create_submitted_purchase_invoice(
			[{"rate": 200}],
			taxes=[(self.output, 5, "Deduct"), (self.input, 5, "Add")],
			posting_date=self.date,
			uae_is_reverse_charge=1,
			uae_reverse_charge_type="Import of Goods",
			uae_is_postponed_import_vat=1,
		)
		# Blocked input tax: not reported.
		create_submitted_purchase_invoice(
			[{"rate": 100, "uae_input_tax_not_recoverable": 1}],
			taxes=[(self.input, 5, "Add")],
			posting_date=self.date,
		)

	def test_generates_every_box(self):
		self._create_period_transactions()
		doc = self.new_return()
		doc.generate_return()
		boxes = _boxes(doc)

		# Box 1: 1000 - 100 (credit note of one unit) in Dubai, 200 in Sharjah.
		self.assertEqual((boxes["1b"].amount, boxes["1b"].vat_amount), (900, 45))
		self.assertEqual((boxes["1c"].amount, boxes["1c"].vat_amount), (200, 10))
		for code in ("1a", "1d", "1e", "1f", "1g"):
			self.assertEqual((boxes[code].amount, boxes[code].vat_amount), (0, 0), code)

		self.assertEqual(boxes["4"].amount, 300)
		self.assertEqual(boxes["5"].amount, 400)
		self.assertEqual((boxes["3"].amount, boxes["3"].vat_amount), (100, 5))
		self.assertEqual((boxes["6"].amount, boxes["6"].vat_amount), (200, 10))
		self.assertEqual(boxes["2"].vat_amount, 0)
		self.assertEqual(boxes["7"].amount, 0)

		# Box 8: amounts 900+200+100+300+400+200, VAT 45+10+5+10.
		self.assertEqual((boxes["8"].amount, boxes["8"].vat_amount), (2100, 70))

		self.assertEqual((boxes["9"].amount, boxes["9"].vat_amount), (500, 25))
		self.assertEqual((boxes["10"].amount, boxes["10"].vat_amount), (300, 15))
		self.assertEqual((boxes["11"].amount, boxes["11"].vat_amount), (800, 40))

		self.assertEqual(doc.total_due_tax, 70)
		self.assertEqual(doc.total_recoverable_tax, 40)
		self.assertEqual(doc.payable_tax, 30)

	def test_regenerating_replaces_the_boxes(self):
		self.sale(rate=1000)
		doc = self.new_return()
		doc.generate_return()
		doc.generate_return()

		self.assertEqual(len(doc.boxes), 17)
		self.assertEqual(_boxes(doc)["1b"].amount, 1000)

	def test_out_of_scope_rows_are_not_reported(self):
		make_item("_Test Out of Scope Item", "Out of Scope")
		self.sale(item="_Test Out of Scope Item", rate=700, vat_rate=0)
		doc = self.new_return()
		doc.generate_return()

		self.assertEqual(_boxes(doc)["8"].amount, 0)

	def test_tourist_refund_reduces_output_vat(self):
		self.sale(rate=1000, uae_tourist_refund=20)
		doc = self.new_return()
		doc.generate_return()

		self.assertEqual(_boxes(doc)["2"].vat_amount, -20)
		self.assertEqual(doc.total_due_tax, 50 - 20)

	def test_invoice_without_emirate_is_refused(self):
		invoice = self.sale(rate=1000)
		frappe.db.set_value("Sales Invoice", invoice.name, "uae_emirate", "")
		doc = self.new_return()

		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.generate_return()
		self.assertIn(invoice.name, str(ctx.exception))

	def test_legacy_rows_without_a_category_fall_back(self):
		"""An invoice from before this app has no VAT category on its rows."""
		zero = self.sale(item="_Test Zero Item", rate=300, vat_rate=0)
		frappe.db.set_value("Sales Invoice Item", zero.items[0].name, "uae_vat_category", "")
		doc = self.new_return()
		doc.generate_return()

		# Falls back to the Item's own category (Zero Rated).
		self.assertEqual(_boxes(doc)["4"].amount, 300)

	def test_requires_an_output_vat_account(self):
		settings = frappe.get_doc("UAE Compliance Settings")
		settings.vat_accounts = []
		settings.save()
		frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")

		self.assertRaises(frappe.ValidationError, self.new_return().generate_return)

	def test_other_companys_invoices_are_excluded(self):
		self.sale(rate=1000)
		doc = frappe.get_doc(
			{
				"doctype": "UAE VAT Return",
				"company": self.company,
				"from_date": frappe.utils.add_days(self.date, -400),
				"to_date": frappe.utils.add_days(self.date, -399),
			}
		).insert()
		doc.generate_return()

		self.assertEqual(_boxes(doc)["8"].amount, 0)


class TestVATReturnLifecycle(VATReturnTestCase):
	def test_period_type_and_due_date_are_derived(self):
		doc = frappe.get_doc(
			{
				"doctype": "UAE VAT Return",
				"company": self.company,
				"from_date": "2026-03-01",
				"to_date": "2026-03-31",
			}
		).insert()

		self.assertEqual(doc.period_type, "Monthly")
		self.assertEqual(str(doc.due_date), "2026-04-28")

	def test_from_date_after_to_date_is_rejected(self):
		doc = frappe.get_doc(
			{
				"doctype": "UAE VAT Return",
				"company": self.company,
				"from_date": "2026-04-01",
				"to_date": "2026-03-01",
			}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_cannot_file_before_generating(self):
		doc = self.new_return()
		self.assertRaises(frappe.ValidationError, doc.mark_as_filed)

	def test_filed_return_is_locked(self):
		self.sale(rate=1000)
		doc = self.new_return()
		doc.generate_return()
		doc.mark_as_filed()

		doc = frappe.get_doc("UAE VAT Return", doc.name)
		self.assertEqual(doc.status, "Filed")
		self.assertRaises(frappe.ValidationError, doc.generate_return)
		self.assertRaises(frappe.ValidationError, doc.mark_as_filed)

		doc.request_refund = 1
		self.assertRaises(frappe.ValidationError, doc.save)
		self.assertRaises(frappe.ValidationError, doc.delete)

	def test_changing_the_period_clears_stale_boxes_and_blocks_filing(self):
		self.sale(rate=1000)
		doc = self.new_return()
		doc.generate_return()
		self.assertTrue(doc.boxes)

		doc.to_date = frappe.utils.add_days(self.date, 1)
		self.assertRaises(frappe.ValidationError, doc.mark_as_filed)

		doc.save()
		self.assertFalse(doc.boxes)
		self.assertEqual(doc.payable_tax, 0)
