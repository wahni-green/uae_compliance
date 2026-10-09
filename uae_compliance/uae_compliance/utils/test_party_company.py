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
