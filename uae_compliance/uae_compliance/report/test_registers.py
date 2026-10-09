from uae_compliance.tests import create_submitted_purchase_invoice
from uae_compliance.uae_compliance.doctype.uae_vat_return.test_uae_vat_return import (
	VATReturnTestCase,
)
from uae_compliance.uae_compliance.report.uae_vat_purchase_register import (
	uae_vat_purchase_register,
)
from uae_compliance.uae_compliance.report.uae_vat_sales_register import uae_vat_sales_register


class TestRegisters(VATReturnTestCase):
	def _filters(self):
		return {"company": self.company, "from_date": self.date, "to_date": self.date}

	def test_sales_register_lists_invoices_by_box(self):
		dubai = self.sale(rate=1000, emirate="Dubai")
		self.sale(item="_Test Zero Item", rate=300, vat_rate=0)
		self.sale(item="_Test Exempt Item", rate=400, vat_rate=0)

		_columns, data = uae_vat_sales_register.execute(self._filters())
		by_box = {row["box"]: row for row in data}

		self.assertEqual(by_box["1b"]["invoice"], dubai.name)
		self.assertEqual((by_box["1b"]["amount"], by_box["1b"]["vat_amount"]), (1000, 50))
		self.assertEqual(by_box["4"]["amount"], 300)
		self.assertEqual(by_box["5"]["amount"], 400)

	def test_sales_register_agrees_with_the_return(self):
		self.sale(rate=1000, emirate="Dubai")
		self.sale(rate=200, emirate="Sharjah")
		doc = self.new_return()
		doc.generate_return()

		_columns, data = uae_vat_sales_register.execute(self._filters())

		self.assertEqual(
			sum(row["amount"] for row in data),
			sum(
				box.amount for box in doc.boxes if box.box_code in ("1a", "1b", "1c", "1d", "1e", "1f", "1g")
			),
		)

	def test_purchase_register_lists_reported_purchases_only(self):
		create_submitted_purchase_invoice(
			[{"rate": 500}], taxes=[(self.input, 5, "Add")], posting_date=self.date
		)
		create_submitted_purchase_invoice(
			[{"rate": 100, "uae_input_tax_not_recoverable": 1}],
			taxes=[(self.input, 5, "Add")],
			posting_date=self.date,
		)

		_columns, data = uae_vat_purchase_register.execute(self._filters())

		self.assertEqual(len(data), 1)
		self.assertEqual(data[0]["box"], "9")
		self.assertEqual((data[0]["amount"], data[0]["recoverable_vat"]), (500, 25))

	def test_filters_are_mandatory(self):
		import frappe

		self.assertRaises(frappe.ValidationError, uae_vat_sales_register.execute, {})
		self.assertRaises(frappe.ValidationError, uae_vat_purchase_register.execute, {})
