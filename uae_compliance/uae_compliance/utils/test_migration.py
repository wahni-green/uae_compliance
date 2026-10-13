import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import get_uae_test_company
from uae_compliance.uae_compliance.utils.migration import (
	backfill_draft_item_rows,
	migrate_master_data,
	migrate_purchase_reverse_charge,
)


def _make_item(code: str):
	return frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": code,
			"item_group": "All Item Groups",
			"stock_uom": "Nos",
			"is_stock_item": 0,
		}
	).insert()


class TestMasterDataMigration(FrappeTestCase):
	def test_customer_tax_id_becomes_trn(self):
		customer = frappe.get_doc(
			{"doctype": "Customer", "customer_name": "_Test Mig Cust", "tax_id": "100-1234-5678-9003"}
		).insert()

		migrate_master_data()

		self.assertEqual(frappe.db.get_value("Customer", customer.name, "uae_trn"), "100123456789003")

	def test_invalid_tax_id_is_not_copied(self):
		customer = frappe.get_doc(
			{"doctype": "Customer", "customer_name": "_Test Mig Bad", "tax_id": "NOT-A-TRN"}
		).insert()

		migrate_master_data()

		self.assertFalse(frappe.db.get_value("Customer", customer.name, "uae_trn"))

	def test_reverse_charge_runs_without_error(self):
		self.assertIsInstance(migrate_purchase_reverse_charge(), int)


class TestDraftRowBackfill(FrappeTestCase):
	def _make_draft_sales_order(self, item_code, **row):
		company = get_uae_test_company()
		customer = frappe.get_doc({"doctype": "Customer", "customer_name": "_Test Backfill Cust"}).insert()
		return frappe.get_doc(
			{
				"doctype": "Sales Order",
				"company": company,
				"customer": customer.name,
				"transaction_date": frappe.utils.today(),
				"delivery_date": frappe.utils.add_days(frappe.utils.today(), 5),
				"items": [{"item_code": item_code, "qty": 1, "rate": 100, **row}],
			}
		).insert()

	def _template(self, category):
		company = get_uae_test_company()
		account = frappe.db.get_value(
			"Account", {"company": company, "is_group": 0, "root_type": "Liability"}, "name"
		)
		return frappe.get_doc(
			{
				"doctype": "Item Tax Template",
				"title": f"_Test Backfill {category}",
				"company": company,
				"uae_vat_category": category,
				"taxes": [{"tax_type": account, "tax_rate": 0}],
			}
		).insert()

	def test_template_category_is_used(self):
		item = _make_item("_Test Backfill Item")
		template = self._template("Standard Rated")
		order = self._make_draft_sales_order(item.name, item_tax_template=template.name)
		frappe.db.set_value("Sales Order Item", order.items[0].name, "uae_vat_category", "")

		backfill_draft_item_rows()

		self.assertEqual(
			frappe.db.get_value("Sales Order Item", order.items[0].name, "uae_vat_category"),
			"Standard Rated",
		)
