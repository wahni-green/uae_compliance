import frappe
from frappe.tests.utils import FrappeTestCase


class TestUAETRN(FrappeTestCase):
	def test_normalizes_and_validates(self):
		doc = frappe.get_doc({"doctype": "UAE TRN", "trn": " 100-1234-5678-9003 "}).insert()
		self.assertEqual(doc.name, "100123456789003")

	def test_rejects_invalid(self):
		doc = frappe.get_doc({"doctype": "UAE TRN", "trn": "12345"})
		self.assertRaises(frappe.ValidationError, doc.insert)
