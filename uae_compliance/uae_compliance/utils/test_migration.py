import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import get_uae_test_company
from uae_compliance.uae_compliance.utils.migration import (
	backfill_draft_item_rows,
	migrate_item_vat_flags,
	migrate_master_data,
	migrate_purchase_reverse_charge,
)


def _make_item(code: str, **flags):
	return frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": code,
			"item_group": "All Item Groups",
			"stock_uom": "Nos",
			"is_stock_item": 0,
			**flags,
		}
	).insert()


class TestItemFlagMigration(FrappeTestCase):
	def setUp(self):
		if not frappe.db.has_column("Item", "is_zero_rated"):
			self.skipTest("ERPNext UAE localization fields are not installed on this site")

	def test_maps_flags_to_vat_category(self):
		zero = _make_item("_Test Mig Zero", is_zero_rated=1)
		exempt = _make_item("_Test Mig Exempt", is_exempt=1)
		plain = _make_item("_Test Mig Plain")

		migrate_item_vat_flags()

		self.assertEqual(frappe.db.get_value("Item", zero.name, "uae_vat_category"), "Zero Rated")
		self.assertEqual(frappe.db.get_value("Item", exempt.name, "uae_vat_category"), "Exempt")
		self.assertFalse(frappe.db.get_value("Item", plain.name, "uae_vat_category"))

	def test_conflict_is_skipped_and_reported(self):
		both = _make_item("_Test Mig Both", is_zero_rated=1, is_exempt=1)

		result = migrate_item_vat_flags()

		self.assertIn(both.name, result["conflicts"])
		self.assertFalse(frappe.db.get_value("Item", both.name, "uae_vat_category"))

	def test_never_overwrites_existing_category(self):
		item = _make_item("_Test Mig Keep", is_zero_rated=1, uae_vat_category="Exempt")

		migrate_item_vat_flags()

		self.assertEqual(frappe.db.get_value("Item", item.name, "uae_vat_category"), "Exempt")

	def test_idempotent(self):
		_make_item("_Test Mig Twice", is_zero_rated=1)
		migrate_item_vat_flags()
		second = migrate_item_vat_flags()

		self.assertEqual(second["items"], 0)

	def test_dry_run_changes_nothing(self):
		item = _make_item("_Test Mig Dry", is_exempt=1)

		result = migrate_item_vat_flags(dry_run=True)

		self.assertGreaterEqual(result["items"], 1)
		self.assertFalse(frappe.db.get_value("Item", item.name, "uae_vat_category"))


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

	def test_template_category_wins_over_item_category(self):
		item = _make_item("_Test Backfill Item", uae_vat_category="Exempt")
		template = self._template("Standard Rated")
		order = self._make_draft_sales_order(item.name, item_tax_template=template.name)
		frappe.db.set_value("Sales Order Item", order.items[0].name, "uae_vat_category", "")

		backfill_draft_item_rows()

		self.assertEqual(
			frappe.db.get_value("Sales Order Item", order.items[0].name, "uae_vat_category"),
			"Standard Rated",
		)

	def test_falls_back_to_item_category_without_template(self):
		item = _make_item("_Test Backfill Item 2", uae_vat_category="Zero Rated")
		order = self._make_draft_sales_order(item.name)
		frappe.db.set_value("Sales Order Item", order.items[0].name, "uae_vat_category", "")

		backfill_draft_item_rows()

		self.assertEqual(
			frappe.db.get_value("Sales Order Item", order.items[0].name, "uae_vat_category"),
			"Zero Rated",
		)
