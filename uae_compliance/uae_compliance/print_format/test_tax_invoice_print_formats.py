import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import (
	configure_vat_settings,
	create_submitted_sales_invoice,
	get_uae_test_company,
	make_address,
	make_customer,
	make_item,
	make_sales_invoice,
	set_company_address,
)
from uae_compliance.uae_compliance.utils.print_data import (
	get_credit_note_values,
	get_tax_invoice_data,
)
from uae_compliance.uae_compliance.utils.qr_code import get_tax_invoice_qr_code


def _print(doc, print_format):
	return frappe.get_print("Sales Invoice", doc.name, print_format=print_format)


class TestTaxInvoicePrintFormats(FrappeTestCase):
	def setUp(self):
		self.company = get_uae_test_company()
		frappe.db.set_value("Company", self.company, "uae_trn", "100123456789003")
		configure_vat_settings(self.company)
		make_customer("_Test UAE Customer", "100987654321003")

	def test_full_layout_has_required_content(self):
		invoice = create_submitted_sales_invoice(customer="_Test UAE Customer")

		html = _print(invoice, "UAE Tax Invoice")

		self.assertIn("<h1>Tax Invoice</h1>", html)
		self.assertIn("100123456789003", html)  # supplier TRN
		self.assertIn("100987654321003", html)  # registered recipient TRN
		self.assertIn(invoice.name, html)
		self.assertIn("5%", html)
		self.assertIn("Total Including VAT", html)

	def test_missing_supplier_details_show_visible_warnings(self):
		frappe.db.set_value("Company", self.company, "uae_trn", "")
		invoice = create_submitted_sales_invoice(customer="_Test UAE Customer")

		html = _print(invoice, "UAE Tax Invoice")

		self.assertIn("Supplier address missing", html)
		self.assertIn("Supplier TRN missing", html)
		self.assertIn("Customer address missing", html)

	def test_supplier_address_is_printed_when_set(self):
		address = set_company_address(self.company)
		invoice = create_submitted_sales_invoice(customer="_Test UAE Customer", company_address=address)

		html = _print(invoice, "UAE Tax Invoice")

		self.assertNotIn("Supplier address missing", html)
		self.assertIn("Sheikh Zayed Road", html)

	def test_unregistered_recipient_has_no_trn_line(self):
		make_customer("_Test Retail Customer")
		invoice = create_submitted_sales_invoice(customer="_Test Retail Customer")

		html = _print(invoice, "UAE Tax Invoice")

		self.assertEqual(html.count("الرقم الضريبي"), 1)  # supplier only

	def test_supply_date_printed_only_when_different(self):
		same = create_submitted_sales_invoice(customer="_Test UAE Customer")
		self.assertNotIn("Supply Date", _print(same, "UAE Tax Invoice"))

		later = create_submitted_sales_invoice(
			customer="_Test UAE Customer",
			uae_supply_date=frappe.utils.add_days(frappe.utils.today(), -3),
		)
		self.assertIn("Supply Date", _print(later, "UAE Tax Invoice"))

	def test_auto_switches_to_simplified_layout_for_flagged_invoice(self):
		make_customer("_Test Retail Customer")
		invoice = create_submitted_sales_invoice(customer="_Test Retail Customer")
		self.assertTrue(invoice.uae_is_simplified_tax_invoice)

		html = _print(invoice, "UAE Tax Invoice")

		self.assertIn("<h1>Tax Invoice</h1>", html)
		self.assertIn("<h3>Simplified</h3>", html)
		self.assertNotIn("Bill To", html)
		self.assertNotIn("Taxable Amount", html)

	def test_standalone_simplified_format_always_renders_simplified(self):
		invoice = create_submitted_sales_invoice(customer="_Test UAE Customer")
		self.assertFalse(invoice.uae_is_simplified_tax_invoice)

		html = _print(invoice, "UAE Simplified Tax Invoice")

		self.assertIn("<h3>Simplified</h3>", html)
		self.assertNotIn("Bill To", html)

	def test_zero_rated_line_shows_zero_percent_and_category(self):
		make_item("_Test Print Zero", "Zero Rated")
		invoice = create_submitted_sales_invoice(
			[{"item_code": "_Test Print Zero", "vat_rate": 0}], customer="_Test UAE Customer"
		)

		html = _print(invoice, "UAE Tax Invoice")

		self.assertIn("0%", html)
		self.assertIn("Zero Rated", html)

	def test_output_vat_account_not_configured_shows_warning_not_zero(self):
		settings = frappe.get_doc("UAE Compliance Settings")
		settings.vat_accounts = []
		settings.save()
		frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")
		doc = make_sales_invoice([{"item_code": "_Test Print Item"}], customer="_Test UAE Customer")
		make_item("_Test Print Item")
		doc.insert()

		html = _print(doc, "UAE Tax Invoice")

		self.assertIn("Output VAT Account not configured", html)


class TestForeignCurrency(FrappeTestCase):
	def test_data_has_aed_amounts_and_rate_disclosure(self):
		company = get_uae_test_company()
		configure_vat_settings(company)
		make_item("_Test FX Item")
		abbr = frappe.get_cached_value("Company", company, "abbr")
		debtors_usd = f"Debtors USD - {abbr}"
		if not frappe.db.exists("Account", debtors_usd):
			frappe.get_doc(
				{
					"doctype": "Account",
					"account_name": "Debtors USD",
					"company": company,
					"parent_account": f"Accounts Receivable - {abbr}",
					"account_type": "Receivable",
					"account_currency": "USD",
				}
			).insert()
		doc = make_sales_invoice(
			[{"item_code": "_Test FX Item"}],
			currency="USD",
			conversion_rate=3.6725,
			debit_to=debtors_usd,
		)
		doc.insert()

		data = get_tax_invoice_data(doc)

		self.assertTrue(data["is_foreign_currency"])
		self.assertEqual(data["company_currency"], "AED")
		self.assertAlmostEqual(data["vat"], 5.0, places=2)
		self.assertAlmostEqual(data["base_vat"], 18.36, places=2)

		html = frappe.get_print("Sales Invoice", doc.name, print_format="UAE Tax Invoice")
		self.assertIn("Exchange rate: 1 USD = 3.6725 AED", html)


class TestTaxCreditNote(FrappeTestCase):
	def setUp(self):
		self.company = get_uae_test_company()
		frappe.db.set_value("Company", self.company, "uae_trn", "100123456789003")
		configure_vat_settings(self.company)
		make_customer("_Test UAE Customer")
		self.original = create_submitted_sales_invoice(customer="_Test UAE Customer")

	def _return(self, qty=-1, reason="Goods returned"):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		doc = make_return_doc("Sales Invoice", self.original.name)
		doc.uae_emirate = "Dubai"
		doc.uae_credit_note_reason = reason
		doc.items[0].qty = qty
		doc.insert()
		return doc

	def test_reason_is_required_to_submit_a_return(self):
		doc = self._return(reason="")
		self.assertRaises(frappe.ValidationError, doc.submit)

	def test_credit_note_values(self):
		doc = self._return()
		doc.submit()

		values = get_credit_note_values(doc)

		self.assertEqual(values["original_value"], 100)
		self.assertEqual(values["difference"], -100)
		self.assertEqual(values["corrected_value"], 0)
		self.assertAlmostEqual(values["tax_on_difference"], -5.0, places=2)

	def test_second_credit_note_starts_from_the_value_left(self):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		original = create_submitted_sales_invoice(
			[{"item_code": "_Test Print Item", "qty": 2}], customer="_Test UAE Customer"
		)

		def make_credit_note():
			doc = make_return_doc("Sales Invoice", original.name)
			doc.uae_emirate = "Dubai"
			doc.uae_credit_note_reason = "Goods returned"
			doc.items[0].qty = -1
			doc.insert()
			doc.submit()
			return doc

		first = get_credit_note_values(make_credit_note())
		self.assertEqual(
			(first["original_value"], first["difference"], first["corrected_value"]), (200, -100, 100)
		)

		second = get_credit_note_values(make_credit_note())
		self.assertEqual(
			(second["original_value"], second["difference"], second["corrected_value"]), (100, -100, 0)
		)

	def test_values_follow_the_order_of_submission_not_of_drafting(self):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		original = create_submitted_sales_invoice(
			[{"item_code": "_Test Print Item", "qty": 3}], customer="_Test UAE Customer"
		)

		def make_draft():
			doc = make_return_doc("Sales Invoice", original.name)
			doc.uae_emirate = "Dubai"
			doc.uae_credit_note_reason = "Goods returned"
			doc.items[0].qty = -1
			doc.insert()
			return doc

		draft_a, draft_b = make_draft(), make_draft()
		draft_b.submit()
		draft_a.submit()

		b = get_credit_note_values(frappe.get_doc("Sales Invoice", draft_b.name))
		a = get_credit_note_values(frappe.get_doc("Sales Invoice", draft_a.name))

		# B was submitted first, so it starts from the full 300 and A from the 200 left.
		self.assertEqual((b["original_value"], b["corrected_value"]), (300, 200))
		self.assertEqual((a["original_value"], a["corrected_value"]), (200, 100))

	def test_return_prints_as_credit_note_in_both_formats(self):
		doc = self._return()
		doc.submit()

		for print_format in ("UAE Tax Invoice", "UAE Tax Credit Note"):
			html = _print(doc, print_format)
			self.assertIn("<h1>Tax Credit Note</h1>", html, print_format)
			self.assertIn(self.original.name, html, print_format)
			self.assertIn("Goods returned", html, print_format)
			self.assertIn("Corrected Value", html, print_format)


class TestQRCode(FrappeTestCase):
	def setUp(self):
		self.company = get_uae_test_company()
		frappe.db.set_value("Company", self.company, "uae_trn", "100123456789003")
		configure_vat_settings(self.company)
		make_customer("_Test UAE Customer")
		self._set_show_qr_code(0)

	def _set_show_qr_code(self, value):
		frappe.db.set_single_value("UAE Compliance Settings", "show_qr_code", value)
		frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")

	def _html(self):
		invoice = create_submitted_sales_invoice(customer="_Test UAE Customer")
		return _print(invoice, "UAE Tax Invoice")

	def test_no_qr_code_by_default(self):
		self.assertNotIn("data:image/png;base64", self._html())

	def test_qr_code_when_enabled(self):
		self._set_show_qr_code(1)

		self.assertIn("data:image/png;base64", self._html())

	def test_no_qr_code_for_einvoicing_company(self):
		configure_vat_settings(self.company, issues_e_invoices=1)
		self._set_show_qr_code(1)

		self.assertNotIn("data:image/png;base64", self._html())

	def test_arabic_company_name_does_not_break_the_payload(self):
		self._set_show_qr_code(1)
		doc = frappe._dict(
			company=self.company, name="X", posting_date="2026-01-01", base_grand_total=105, taxes=[]
		)
		frappe.db.set_value("Company", self.company, "uae_trn", "100123456789003")
		self.assertTrue(get_tax_invoice_qr_code(doc).startswith("data:image/png;base64"))
