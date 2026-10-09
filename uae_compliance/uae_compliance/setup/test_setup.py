import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.uae_compliance.constants.custom_fields import CUSTOM_FIELDS
from uae_compliance.uae_compliance.constants.erpnext_uae_fields import ERPNEXT_UAE_FIELDS
from uae_compliance.uae_compliance.setup import create_custom_fields, hide_erpnext_uae_fields


class TestSetup(FrappeTestCase):
	def test_custom_fields_exist_and_are_uae_prefixed(self):
		create_custom_fields()
		for doctypes, fields in CUSTOM_FIELDS.items():
			for doctype in [doctypes] if isinstance(doctypes, str) else doctypes:
				for field in fields:
					self.assertTrue(field["fieldname"].startswith("uae_"), field["fieldname"])
					self.assertTrue(
						frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field["fieldname"]}),
						f"{doctype}.{field['fieldname']}",
					)

	def test_vat_category_select_has_leading_blank(self):
		create_custom_fields()
		options = frappe.get_meta("Sales Invoice Item").get_field("uae_vat_category").options
		self.assertTrue(options.startswith("\n"))

	def test_hide_erpnext_uae_fields_is_idempotent(self):
		hide_erpnext_uae_fields()
		hide_erpnext_uae_fields()

		for doctype, fieldnames in ERPNEXT_UAE_FIELDS.items():
			for fieldname in fieldnames:
				if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname}):
					continue

				count = frappe.db.count(
					"Property Setter",
					{"doc_type": doctype, "field_name": fieldname, "property": "hidden"},
				)
				self.assertEqual(count, 1, f"{doctype}.{fieldname}")

	def test_no_doctype_name_clashes_with_other_apps(self):
		ours = frappe.get_all("DocType", filters={"module": "UAE Compliance"}, pluck="name")
		self.assertTrue(ours)
		for name in ours:
			self.assertEqual(frappe.db.get_value("DocType", name, "module"), "UAE Compliance")
			self.assertTrue(name.startswith("UAE "), name)
