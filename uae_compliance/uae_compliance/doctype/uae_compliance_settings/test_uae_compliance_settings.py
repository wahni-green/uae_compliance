import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import get_uae_test_company


class TestUAEComplianceSettings(FrappeTestCase):
	def setUp(self):
		self.settings = frappe.get_doc("UAE Compliance Settings")

	def test_defaults(self):
		self.assertEqual(self.settings.settings_currency, "AED")
		self.assertEqual(self.settings.simplified_tax_invoice_threshold, 10000)
		self.assertEqual(self.settings.mandatory_registration_threshold, 375000)
		self.assertEqual(self.settings.voluntary_registration_threshold, 187500)

	def test_rejects_duplicate_company_rows(self):
		company = get_uae_test_company()
		account = frappe.db.get_value("Account", {"company": company, "is_group": 0}, "name")
		self.settings.vat_accounts = []
		for _ in range(2):
			self.settings.append("vat_accounts", {"company": company, "output_vat_account": account})

		self.assertRaises(frappe.ValidationError, self.settings.validate)

	def test_rejects_invalid_regex(self):
		self.settings.vat_accounts = []
		self.settings.trn_pattern = "([unclosed"
		self.assertRaises(frappe.ValidationError, self.settings.validate)

	def test_rejects_account_of_another_company(self):
		company = get_uae_test_company()
		other = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": "_Test Other VAT Co",
				"abbr": "TOV",
				"default_currency": "AED",
				"country": "United Arab Emirates",
			}
		).insert()
		foreign = frappe.db.get_value("Account", {"company": other.name, "is_group": 0}, "name")
		self.settings.vat_accounts = []
		self.settings.append("vat_accounts", {"company": company, "output_vat_account": foreign})

		self.assertRaises(frappe.ValidationError, self.settings.validate)

	def test_rejects_group_account(self):
		company = get_uae_test_company()
		group = frappe.db.get_value("Account", {"company": company, "is_group": 1}, "name")
		self.settings.vat_accounts = []
		self.settings.append("vat_accounts", {"company": company, "output_vat_account": group})

		self.assertRaises(frappe.ValidationError, self.settings.validate)
