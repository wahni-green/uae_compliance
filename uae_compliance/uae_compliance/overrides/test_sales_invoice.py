from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import (
	configure_vat_settings,
	get_uae_test_company,
	make_address,
	make_customer,
	make_item,
	make_sales_invoice,
)


class TestSalesInvoice(FrappeTestCase):
	def setUp(self):
		self.company = get_uae_test_company()
		self.output, self.input = configure_vat_settings(self.company)
		self.standard = make_item("_Test Std Item")
		self.zero = make_item("_Test Zero Item", "Zero Rated")

	def _template(self, category, rate=0):
		name = f"_Test SI {category} - {frappe.get_cached_value('Company', self.company, 'abbr')}"
		if frappe.db.exists("Item Tax Template", name):
			return frappe.get_doc("Item Tax Template", name)

		return frappe.get_doc(
			{
				"doctype": "Item Tax Template",
				"title": f"_Test SI {category}",
				"company": self.company,
				"uae_vat_category": category,
				"taxes": [{"tax_type": self.output, "tax_rate": rate}],
			}
		).insert()

	def test_blank_category_defaults_to_standard_rated(self):
		doc = make_sales_invoice([{"item_code": self.standard.name}])
		doc.insert()
		self.assertEqual(doc.items[0].uae_vat_category, "Standard Rated")

	def test_category_from_item_master(self):
		doc = make_sales_invoice([{"item_code": self.zero.name, "vat_rate": 0}])
		doc.insert()
		self.assertEqual(doc.items[0].uae_vat_category, "Zero Rated")

	def test_category_from_item_tax_template_beats_item_master(self):
		template = self._template("Exempt")
		doc = make_sales_invoice(
			[{"item_code": self.standard.name, "item_tax_template": template.name, "vat_rate": 0}]
		)
		doc.insert()
		self.assertEqual(doc.items[0].uae_vat_category, "Exempt")

	def test_never_overwrites_explicit_category(self):
		doc = make_sales_invoice(
			[{"item_code": self.standard.name, "uae_vat_category": "Out of Scope", "vat_rate": 0}]
		)
		doc.insert()
		self.assertEqual(doc.items[0].uae_vat_category, "Out of Scope")

	def test_zero_rated_row_charged_vat_is_rejected(self):
		doc = make_sales_invoice([{"item_code": self.zero.name}])
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_zero_rated_row_with_zero_vat_is_accepted(self):
		make_sales_invoice([{"item_code": self.zero.name, "vat_rate": 0}]).insert()

	def test_row_category_must_match_item_tax_template(self):
		template = self._template("Exempt")
		doc = make_sales_invoice(
			[
				{
					"item_code": self.standard.name,
					"item_tax_template": template.name,
					"uae_vat_category": "Standard Rated",
				}
			]
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_same_item_with_mixed_categories_is_rejected(self):
		doc = make_sales_invoice(
			[
				{"item_code": self.standard.name, "uae_vat_category": "Standard Rated"},
				{"item_code": self.standard.name, "uae_vat_category": "Zero Rated", "vat_rate": 0},
			]
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_export_flag_from_shipping_address_country(self):
		customer = make_customer("_Test UAE Customer")
		address = make_address("_Test Export Addr", "India", customer=customer.name)
		doc = make_sales_invoice(
			[{"item_code": self.zero.name, "vat_rate": 0}],
			customer=customer.name,
			shipping_address_name=address.name,
		)
		doc.insert()
		self.assertTrue(doc.uae_is_export)

	def test_domestic_invoice_is_not_export(self):
		doc = make_sales_invoice([{"item_code": self.standard.name}])
		doc.insert()
		self.assertFalse(doc.uae_is_export)

	def test_simplified_flag_for_small_unregistered_customer(self):
		make_customer("_Test Retail Customer")
		doc = make_sales_invoice([{"item_code": self.standard.name}], customer="_Test Retail Customer")
		doc.insert()
		self.assertTrue(doc.uae_is_simplified_tax_invoice)

	def test_no_simplified_flag_for_registered_customer(self):
		make_customer("_Test Registered Customer", "100123456789003")
		doc = make_sales_invoice([{"item_code": self.standard.name}], customer="_Test Registered Customer")
		doc.insert()
		self.assertFalse(doc.uae_is_simplified_tax_invoice)

	def test_no_simplified_flag_above_threshold(self):
		make_customer("_Test Retail Customer")
		doc = make_sales_invoice(
			[{"item_code": self.standard.name, "rate": 20000}], customer="_Test Retail Customer"
		)
		doc.insert()
		self.assertFalse(doc.uae_is_simplified_tax_invoice)

	def test_no_simplified_flag_for_einvoicing_company(self):
		configure_vat_settings(self.company, issues_e_invoices=1)
		make_customer("_Test Retail Customer")
		doc = make_sales_invoice([{"item_code": self.standard.name}], customer="_Test Retail Customer")
		doc.insert()
		self.assertFalse(doc.uae_is_simplified_tax_invoice)

	def test_submit_requires_emirate_for_standard_rated(self):
		doc = make_sales_invoice([{"item_code": self.standard.name}])
		doc.insert()
		doc.uae_emirate = ""
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.submit()
		self.assertIn("VAT Emirate", str(ctx.exception))

	def test_submit_with_emirate_succeeds(self):
		doc = make_sales_invoice([{"item_code": self.standard.name}])
		doc.insert()
		doc.uae_emirate = "Dubai"
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def test_zero_rated_only_invoice_does_not_need_emirate(self):
		from uae_compliance.uae_compliance.overrides.sales_invoice import validate_emirate

		doc = make_sales_invoice([{"item_code": self.zero.name, "vat_rate": 0}])
		doc.insert()
		doc.uae_emirate = ""
		validate_emirate(doc)

	def test_non_uae_company_is_not_checked(self):
		from uae_compliance.uae_compliance.overrides.sales_invoice import validate

		doc = make_sales_invoice([{"item_code": self.zero.name, "uae_vat_category": "Zero Rated"}])
		with patch(
			"uae_compliance.uae_compliance.overrides.sales_invoice.is_uae_company", return_value=False
		):
			validate(doc)

		self.assertFalse(doc.get("uae_is_export"))
		self.assertFalse(doc.items[0].get("uae_vat_category") is None)

	def test_late_tax_invoice_warns(self):
		from uae_compliance.uae_compliance.overrides.sales_invoice import warn_late_tax_invoice

		today = frappe.utils.today()
		doc = frappe._dict(posting_date=today, uae_supply_date=frappe.utils.add_days(today, -20), is_return=0)
		with patch("uae_compliance.uae_compliance.overrides.sales_invoice.frappe.msgprint") as msg:
			warn_late_tax_invoice(doc)
		msg.assert_called_once()

		doc.uae_supply_date = frappe.utils.add_days(today, -10)
		with patch("uae_compliance.uae_compliance.overrides.sales_invoice.frappe.msgprint") as msg:
			warn_late_tax_invoice(doc)
		msg.assert_not_called()
