import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import get_uae_test_company


class TestTRNOnMasters(FrappeTestCase):
	def test_customer_trn_is_validated_and_normalized(self):
		customer = frappe.get_doc(
			{"doctype": "Customer", "customer_name": "_Test UAE Customer", "uae_trn": "100-1234-5678-9003"}
		).insert()
		self.assertEqual(customer.uae_trn, "100123456789003")

		customer.uae_trn = "bad"
		self.assertRaises(frappe.ValidationError, customer.save)

	def test_supplier_tin_is_validated(self):
		supplier = frappe.get_doc({"doctype": "Supplier", "supplier_name": "_Test UAE Supplier"})
		supplier.uae_tin = "123"
		self.assertRaises(frappe.ValidationError, supplier.insert)

	def test_company_trn_is_validated(self):
		company = frappe.get_doc("Company", get_uae_test_company())
		company.uae_trn = "999"
		self.assertRaises(frappe.ValidationError, company.save)


class TestLegalRegistrationOnParties(FrappeTestCase):
	def customer(self, **kwargs):
		return frappe.get_doc({"doctype": "Customer", "customer_name": "_Test UAE Registration", **kwargs})

	def test_an_id_without_a_type_is_refused(self):
		customer = self.customer(uae_legal_registration_id="112345679000001")
		self.assertRaises(frappe.ValidationError, customer.insert)

	def test_a_trade_license_needs_its_authority(self):
		customer = self.customer(uae_legal_registration_type="Trade License")
		self.assertRaises(frappe.ValidationError, customer.insert)

		customer.uae_licence_authority = "Dubai Economy"
		customer.insert()

	def test_a_passport_needs_its_country(self):
		customer = self.customer(uae_legal_registration_type="Passport")
		self.assertRaises(frappe.ValidationError, customer.insert)

		customer.uae_passport_country = "India"
		customer.insert()

	def test_a_customer_without_a_registration_is_accepted(self):
		self.customer().insert()
