import frappe
from frappe.tests.utils import FrappeTestCase


class TestUAETRN(FrappeTestCase):
	def test_normalizes_and_validates(self):
		doc = frappe.get_doc({"doctype": "UAE TRN", "trn": " 100-1234-5678-9003 "}).insert()
		self.assertEqual(doc.name, "100123456789003")

	def test_rejects_invalid(self):
		doc = frappe.get_doc({"doctype": "UAE TRN", "trn": "12345"})
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_trn_cannot_diverge_from_name_after_creation(self):
		doc = frappe.get_doc({"doctype": "UAE TRN", "trn": "100555555555003"}).insert()

		doc.trn = "bad"
		self.assertRaises(frappe.ValidationError, doc.save)

		doc.trn = "100999999999003"
		self.assertRaises(frappe.ValidationError, doc.save)
