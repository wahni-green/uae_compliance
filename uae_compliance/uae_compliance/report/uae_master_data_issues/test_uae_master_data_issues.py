import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import make_address, make_customer
from uae_compliance.uae_compliance.report.uae_master_data_issues import uae_master_data_issues


class TestMasterDataIssues(FrappeTestCase):
	def issues_of(self, document):
		_columns, data = uae_master_data_issues.execute()
		return [row["issue"] for row in data if row["document"] == document]

	def test_a_customer_saved_before_the_rules_is_listed(self):
		customer = make_customer("_Test Issue Customer")
		frappe.db.set_value(
			"Customer",
			customer.name,
			{"uae_legal_registration_id": "112345679000001", "uae_legal_registration_type": ""},
		)

		self.assertEqual(len(self.issues_of(customer.name)), 1)

	def test_a_clean_customer_is_not_listed(self):
		customer = make_customer("_Test Clean Customer")

		self.assertEqual(self.issues_of(customer.name), [])

	def test_an_address_without_an_emirate_is_listed(self):
		address = make_address("_Test Issue Address", "United Arab Emirates", uae_emirate="Dubai")
		frappe.db.set_value("Address", address.name, "uae_emirate", "")

		self.assertEqual(len(self.issues_of(address.name)), 1)

	def test_an_address_with_another_spelling_of_the_country_is_listed(self):
		if not frappe.db.exists("Country", "UAE"):
			frappe.get_doc({"doctype": "Country", "country_name": "UAE", "code": "uae-alias"}).insert()

		address = make_address("_Test Alias Address", "UAE")

		self.assertEqual(len(self.issues_of(address.name)), 1)
