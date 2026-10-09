import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.uae_compliance.utils.trn import validate_tin, validate_trn


class TestTRN(FrappeTestCase):
	def test_blank_is_unchanged(self):
		self.assertIsNone(validate_trn(None))
		self.assertEqual(validate_trn(""), "")

	def test_normalizes_spaces_and_hyphens(self):
		self.assertEqual(validate_trn("100-1234-5678-9003"), "100123456789003")
		self.assertEqual(validate_trn(" 100123456789003 "), "100123456789003")

	def test_rejects_bad_trn(self):
		for bad in ("12345", "200123456789003", "10012345678900X", "1001234567890031"):
			with self.assertRaises(frappe.ValidationError, msg=bad):
				validate_trn(bad)

	def test_unanchored_pattern_still_matches_whole_value(self):
		old = frappe.db.get_single_value("UAE Compliance Settings", "trn_pattern")
		self.addCleanup(lambda: frappe.db.set_single_value("UAE Compliance Settings", "trn_pattern", old))
		frappe.db.set_single_value("UAE Compliance Settings", "trn_pattern", r"100[0-9]{12}")
		frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")

		self.assertRaises(frappe.ValidationError, validate_trn, "100123456789003999")

	def test_tin(self):
		self.assertEqual(validate_tin("1234567890"), "1234567890")
		with self.assertRaises(frappe.ValidationError):
			validate_tin("2234567890")

	def test_pattern_is_configurable(self):
		settings = frappe.get_doc("UAE Compliance Settings")
		old = settings.trn_pattern
		self.addCleanup(lambda: frappe.db.set_single_value("UAE Compliance Settings", "trn_pattern", old))
		frappe.db.set_single_value("UAE Compliance Settings", "trn_pattern", r"^[0-9]{15}$")
		frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")

		self.assertEqual(validate_trn("200123456789003"), "200123456789003")
