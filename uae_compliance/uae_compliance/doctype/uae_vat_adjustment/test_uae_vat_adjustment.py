import frappe
from frappe.utils import add_months

from uae_compliance.tests import create_submitted_purchase_invoice, make_item, make_sales_invoice
from uae_compliance.uae_compliance.doctype.uae_vat_return.test_uae_vat_return import (
	VATReturnTestCase,
	_boxes,
)

# Test records for Sales and Purchase Invoice pull in every linked doctype recursively, including
# ones that are not installed; these tests build the invoices they need themselves.
test_ignore = ["Sales Invoice", "Purchase Invoice"]


class TestUAEVATAdjustment(VATReturnTestCase):
	def _relief(self, invoice, **kwargs):
		return frappe.get_doc(
			{
				"doctype": "UAE VAT Adjustment",
				"company": self.company,
				"adjustment_type": "Bad Debt Relief",
				"sales_invoice": invoice.name,
				"emirate": "Dubai",
				"posting_date": add_months(self.date, 7),
				"write_off_date": add_months(self.date, 7),
				"customer_notified": 1,
				"notification_date": add_months(self.date, 7),
				"vat_amount": -20,
				**kwargs,
			}
		)

	def _return_for(self, posting_date):
		return frappe.get_doc(
			{
				"doctype": "UAE VAT Return",
				"company": self.company,
				"from_date": posting_date,
				"to_date": posting_date,
			}
		).insert()

	def test_bad_debt_relief_is_accepted_after_six_months(self):
		invoice = self.sale(rate=1000)
		self._relief(invoice).insert()

	def test_relief_too_early_is_rejected(self):
		invoice = self.sale(rate=1000)
		doc = self._relief(invoice, posting_date=add_months(self.date, 5))
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_relief_needs_the_customer_to_be_notified(self):
		invoice = self.sale(rate=1000)
		doc = self._relief(invoice, customer_notified=0)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_relief_must_be_negative(self):
		invoice = self.sale(rate=1000)
		doc = self._relief(invoice, vat_amount=20)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_relief_cannot_exceed_the_vat_charged(self):
		invoice = self.sale(rate=1000)
		doc = self._relief(invoice, vat_amount=-51)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_earlier_reliefs_count_towards_the_limit(self):
		invoice = self.sale(rate=1000)
		first = self._relief(invoice, vat_amount=-30).insert()
		first.submit()

		second = self._relief(invoice, vat_amount=-30)
		self.assertRaises(frappe.ValidationError, second.insert)

		self._relief(invoice, vat_amount=-20).insert()

	def test_relief_must_be_for_a_submitted_invoice_of_the_company(self):
		make_item("_Test Print Item")
		draft = make_sales_invoice(
			[{"item_code": "_Test Print Item"}],
			customer="_Test UAE Customer",
			posting_date=self.date,
		).insert()
		self.assertEqual(draft.docstatus, 0)
		doc = self._relief(draft)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_relief_reduces_output_vat_in_the_adjustment_column(self):
		invoice = self.sale(rate=1000)
		relief = self._relief(invoice, vat_amount=-20).insert()
		relief.submit()

		doc = self._return_for(add_months(self.date, 7))
		doc.generate_return()
		boxes = _boxes(doc)

		self.assertEqual(boxes["1b"].adjustment, -20)
		self.assertEqual(boxes["8"].adjustment, -20)
		self.assertEqual(doc.total_due_tax, -20)

	def test_draft_and_cancelled_adjustments_are_ignored(self):
		invoice = self.sale(rate=1000)
		self._relief(invoice).insert()

		doc = self._return_for(add_months(self.date, 7))
		doc.generate_return()

		self.assertEqual(_boxes(doc)["1b"].adjustment, 0)

	def test_bad_debt_repayment_reduces_recoverable_vat(self):
		purchase = create_submitted_purchase_invoice(
			[{"rate": 500}], taxes=[(self.input, 5, "Add")], posting_date=self.date
		)
		repayment = frappe.get_doc(
			{
				"doctype": "UAE VAT Adjustment",
				"company": self.company,
				"adjustment_type": "Bad Debt Repayment",
				"purchase_invoice": purchase.name,
				"posting_date": add_months(self.date, 8),
				"notification_date": add_months(self.date, 1),
				"vat_amount": -10,
			}
		).insert()
		repayment.submit()

		doc = self._return_for(add_months(self.date, 8))
		doc.generate_return()

		self.assertEqual(_boxes(doc)["9"].adjustment, -10)
		self.assertEqual(doc.total_recoverable_tax, -10)

	def test_repayment_too_soon_after_the_notice_is_rejected(self):
		purchase = create_submitted_purchase_invoice(
			[{"rate": 500}], taxes=[(self.input, 5, "Add")], posting_date=self.date
		)
		doc = frappe.get_doc(
			{
				"doctype": "UAE VAT Adjustment",
				"company": self.company,
				"adjustment_type": "Bad Debt Repayment",
				"purchase_invoice": purchase.name,
				"posting_date": add_months(self.date, 3),
				"notification_date": add_months(self.date, 1),
				"vat_amount": -10,
			}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_import_adjustment_goes_to_box_7(self):
		date = add_months(self.date, 9)
		adjustment = frappe.get_doc(
			{
				"doctype": "UAE VAT Adjustment",
				"company": self.company,
				"adjustment_type": "Import Adjustment",
				"posting_date": date,
				"amount": 1000,
				"vat_amount": 50,
			}
		).insert()
		adjustment.submit()

		doc = self._return_for(date)
		doc.generate_return()
		boxes = _boxes(doc)

		self.assertEqual((boxes["7"].amount, boxes["7"].vat_amount), (1000, 50))
		self.assertEqual((boxes["8"].amount, boxes["8"].vat_amount), (1000, 50))
		self.assertEqual(doc.total_due_tax, 50)

	def test_cannot_submit_an_empty_adjustment(self):
		doc = frappe.get_doc(
			{
				"doctype": "UAE VAT Adjustment",
				"company": self.company,
				"adjustment_type": "Capital Assets Scheme",
				"posting_date": self.date,
				"vat_amount": 0,
			}
		).insert()
		self.assertRaises(frappe.ValidationError, doc.submit)
