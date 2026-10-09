import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import (
	configure_vat_settings,
	get_uae_test_company,
	get_vat_accounts,
	make_address,
	make_item,
)


class TestPurchaseInvoice(FrappeTestCase):
	def setUp(self):
		self.company = get_uae_test_company()
		self.output, self.input = get_vat_accounts(self.company)
		self.item = make_item("_Test Purchase Item")
		if not frappe.db.exists("Supplier", "_Test UAE Supplier"):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": "_Test UAE Supplier"}).insert()

	def _invoice(self, rc_rows=(), **kwargs):
		taxes = [
			{
				"charge_type": "On Net Total",
				"account_head": account,
				"description": "VAT",
				"rate": rate,
				"add_deduct_tax": add_deduct,
				"category": "Total",
			}
			for account, rate, add_deduct in rc_rows
		]
		return frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": self.company,
				"supplier": "_Test UAE Supplier",
				"posting_date": frappe.utils.today(),
				"set_posting_time": 1,
				"bill_no": "B1",
				"items": [{"item_code": self.item.name, "qty": 1, "rate": 100}],
				"taxes": taxes,
				**kwargs,
			}
		)

	def test_default_category(self):
		doc = self._invoice()
		doc.insert()
		self.assertEqual(doc.items[0].uae_vat_category, "Standard Rated")

	def test_reverse_charge_needs_configured_accounts(self):
		settings = frappe.get_doc("UAE Compliance Settings")
		settings.vat_accounts = []
		settings.save()
		frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")

		doc = self._invoice(uae_is_reverse_charge=1, uae_reverse_charge_type="Import of Services")
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_reverse_charge_needs_output_and_input_rows(self):
		configure_vat_settings(self.company)
		only_output = self._invoice(
			rc_rows=[(self.output, 5, "Add")],
			uae_is_reverse_charge=1,
			uae_reverse_charge_type="Import of Services",
		)
		self.assertRaises(frappe.ValidationError, only_output.insert)

		only_input = self._invoice(
			rc_rows=[(self.input, 5, "Deduct")],
			uae_is_reverse_charge=1,
			uae_reverse_charge_type="Import of Services",
		)
		self.assertRaises(frappe.ValidationError, only_input.insert)

	def test_reverse_charge_with_both_rows_is_accepted(self):
		configure_vat_settings(self.company)
		doc = self._invoice(
			rc_rows=[(self.output, 5, "Add"), (self.input, 5, "Deduct")],
			uae_is_reverse_charge=1,
			uae_reverse_charge_type="Import of Services",
		)
		doc.insert()

	def test_metal_scrap_needs_declaration(self):
		configure_vat_settings(self.company)
		rows = [(self.output, 5, "Add"), (self.input, 5, "Deduct")]
		without = self._invoice(rc_rows=rows, uae_is_reverse_charge=1, uae_reverse_charge_type="Metal Scrap")
		self.assertRaises(frappe.ValidationError, without.insert)

		with_declaration = self._invoice(
			rc_rows=rows,
			uae_is_reverse_charge=1,
			uae_reverse_charge_type="Metal Scrap",
			uae_rc_declaration=1,
		)
		with_declaration.insert()

	def test_gcc_supplier_flag(self):
		address = make_address("_Test Saudi Supplier", "Saudi Arabia", supplier="_Test UAE Supplier")
		doc = self._invoice(supplier_address=address.name)
		doc.insert()
		self.assertTrue(doc.uae_is_gcc_supplier)

	def test_non_gcc_supplier_flag(self):
		address = make_address("_Test Indian Supplier", "India", supplier="_Test UAE Supplier")
		doc = self._invoice(supplier_address=address.name)
		doc.insert()
		self.assertFalse(doc.uae_is_gcc_supplier)

	def test_import_of_goods_from_dispatch_address(self):
		address = make_address("_Test Dispatch India", "India", supplier="_Test UAE Supplier")
		doc = self._invoice(dispatch_address=address.name)
		doc.insert()
		self.assertTrue(doc.uae_is_import_of_goods)

	def test_postponed_import_vat_requires_import_of_goods(self):
		doc = self._invoice(uae_is_postponed_import_vat=1)
		self.assertRaises(frappe.ValidationError, doc.insert)
