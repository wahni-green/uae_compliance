from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import (
	configure_vat_settings,
	disable_einvoicing,
	enable_einvoicing,
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

	def test_exempt_row_charged_vat_is_rejected(self):
		doc = make_sales_invoice([{"item_code": self.standard.name, "uae_vat_category": "Exempt"}])
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_zero_rated_item_is_not_charged_vat(self):
		doc = make_sales_invoice([{"item_code": self.zero.name}])
		doc.insert()
		self.assertEqual(doc.total_taxes_and_charges, 0)

	def test_zero_rated_row_with_zero_vat_is_accepted(self):
		make_sales_invoice([{"item_code": self.zero.name, "vat_rate": 0}]).insert()

	def test_row_category_follows_item_tax_template(self):
		template = self._template("Exempt")
		doc = make_sales_invoice(
			[
				{
					"item_code": self.standard.name,
					"item_tax_template": template.name,
					"uae_vat_category": "Standard Rated",
					"vat_rate": 0,
				}
			]
		)
		doc.insert()
		self.assertEqual(doc.items[0].uae_vat_category, "Exempt")

	def test_a_row_without_a_template_follows_the_vat_charged(self):
		doc = make_sales_invoice([{"item_code": self.standard.name}]).insert()
		self.assertEqual(doc.items[0].uae_vat_category, "Standard Rated")

		doc.taxes = []
		doc.save()
		self.assertEqual(doc.items[0].uae_vat_category, "Zero Rated")

	def test_changing_the_item_tax_template_changes_the_category(self):
		doc = make_sales_invoice([{"item_code": self.standard.name}]).insert()
		self.assertEqual(doc.items[0].uae_vat_category, "Standard Rated")

		doc.items[0].item_tax_template = self._template("Zero Rated").name
		doc.save()
		self.assertEqual(doc.items[0].uae_vat_category, "Zero Rated")

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
		previous = enable_einvoicing(self.company)
		self.addCleanup(disable_einvoicing, self.company, previous)
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

	def test_einvoice_log_is_listed_in_connections(self):
		from frappe.desk.notifications import get_open_count

		doc = make_sales_invoice([{"item_code": self.standard.name}])
		doc.insert()
		frappe.get_doc(
			{
				"doctype": "UAE E-Invoice Log",
				"company": self.company,
				"direction": "Outbound",
				"status": "Pending",
				"reference_doctype": "Sales Invoice",
				"reference_name": doc.name,
			}
		).insert(ignore_permissions=True, ignore_mandatory=True)

		counts = get_open_count("Sales Invoice", doc.name)["count"]["external_links_found"]
		self.assertEqual([c["count"] for c in counts if c["doctype"] == "UAE E-Invoice Log"], [1])

	def test_supply_date_defaults(self):
		from uae_compliance.uae_compliance.overrides.sales_invoice import set_supply_date

		today = frappe.utils.today()
		doc = frappe._dict(update_stock=1, posting_date=today, items=[])
		set_supply_date(doc)
		self.assertEqual(doc.uae_supply_date, today)

		doc = frappe._dict(update_stock=1, posting_date=today, uae_supply_date="2020-01-01", items=[])
		set_supply_date(doc)
		self.assertEqual(doc.uae_supply_date, "2020-01-01")

		early, late = frappe.utils.add_days(today, -9), frappe.utils.add_days(today, -5)
		notes = [
			frappe._dict(name=f"_DN{i}", posting_date=d)
			for i, d in enumerate((late, early))
		]
		rows = [frappe._dict(delivery_note=n.name) for n in notes]
		doc = frappe._dict(update_stock=0, posting_date=today, items=rows)
		with patch(
			"uae_compliance.uae_compliance.overrides.sales_invoice.frappe.get_all",
			return_value=[n.posting_date for n in notes],
		):
			set_supply_date(doc)
		self.assertEqual(doc.uae_supply_date, early)

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
