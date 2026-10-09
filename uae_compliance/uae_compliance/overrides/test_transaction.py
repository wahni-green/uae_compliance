import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import (
	get_uae_test_company,
	make_address,
	make_customer,
	make_item,
)


class TestTransaction(FrappeTestCase):
	def _sales_order(self, item, **kwargs):
		make_customer("_Test UAE Customer")
		return frappe.get_doc(
			{
				"doctype": "Sales Order",
				"company": get_uae_test_company(),
				"customer": "_Test UAE Customer",
				"transaction_date": frappe.utils.today(),
				"delivery_date": frappe.utils.add_days(frappe.utils.today(), 3),
				"items": [{"item_code": item, "qty": 1, "rate": 100}],
				**kwargs,
			}
		)

	def test_defaults_from_item_master(self):
		item = make_item("_Test Exempt Item", "Exempt")
		doc = self._sales_order(item.name)
		doc.insert()
		self.assertEqual(doc.items[0].uae_vat_category, "Exempt")

	def test_defaults_to_standard_rated(self):
		item = make_item("_Test Plain Item")
		doc = self._sales_order(item.name)
		doc.insert()
		self.assertEqual(doc.items[0].uae_vat_category, "Standard Rated")

	def test_designated_zone_address_never_auto_zero_rates(self):
		zone = frappe.get_all("UAE Designated Zone", pluck="name", limit=1)[0]
		address = make_address(
			"_Test Zone Addr", "United Arab Emirates", customer="_Test UAE Customer", uae_designated_zone=zone
		)
		item = make_item("_Test Zone Item")
		doc = self._sales_order(item.name, customer_address=address.name)
		doc.insert()
		self.assertEqual(doc.items[0].uae_vat_category, "Standard Rated")
