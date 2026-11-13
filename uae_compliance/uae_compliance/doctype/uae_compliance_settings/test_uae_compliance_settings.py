import json

import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import get_uae_test_company
from uae_compliance.uae_compliance.einvoice import registry
from uae_compliance.uae_compliance.einvoice.asp_client import (
	ASPClient,
	StatusResult,
	SubmitResult,
)


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

	def test_rejects_same_input_and_output_account(self):
		company = get_uae_test_company()
		account = frappe.db.get_value("Account", {"company": company, "is_group": 0}, "name")
		self.settings.vat_accounts = []
		self.settings.append(
			"vat_accounts",
			{"company": company, "output_vat_account": account, "input_vat_account": account},
		)

		self.assertRaises(frappe.ValidationError, self.settings.validate)

	def test_rejects_same_excise_and_vat_account(self):
		company = get_uae_test_company()
		account = frappe.db.get_value("Account", {"company": company, "is_group": 0}, "name")
		for fieldname in ("output_vat_account", "input_vat_account"):
			self.settings.vat_accounts = []
			self.settings.append(
				"vat_accounts", {"company": company, fieldname: account, "excise_tax_account": account}
			)

			self.assertRaises(frappe.ValidationError, self.settings.validate)


class DemoASP(ASPClient):
	name = "Demo"
	required_settings = ("endpoint_url", "client_id", "client_secret")

	def submit(self, document, idempotency_key):
		return SubmitResult("DEMO-1", "Submitted")

	def get_status(self, provider_reference):
		return StatusResult("Cleared")


class TestUAEEInvoiceCompanies(FrappeTestCase):
	def setUp(self):
		self.company = get_uae_test_company()
		self.settings = self._fresh()

	def register_demo(self):
		"""Make the Demo provider selectable for the length of a test."""
		registry.register_provider(DemoASP)
		self.addCleanup(registry._PROVIDERS.pop, "Demo", None)

		field = frappe.get_meta("UAE E-Invoice Company Setting").get_field("provider")
		options = field.options
		field.options = f"{options}\nDemo"
		self.addCleanup(setattr, field, "options", options)

	def _fresh(self):
		settings = frappe.get_doc("UAE Compliance Settings")
		settings.companies = []
		return settings

	def _row(self, **values):
		self.settings.append(
			"companies",
			{"company": self.company, "enabled": 1, "provider": "Mock", "environment": "Sandbox", **values},
		)

	def test_the_mock_provider_is_always_available(self):
		self.assertIn("Mock", registry.get_provider_names())

	def test_every_provider_can_be_selected(self):
		options = frappe.get_meta("UAE E-Invoice Company Setting").get_field("provider").options
		self.assertEqual(options.split("\n"), registry.get_provider_names())

	def test_valid_settings_save(self):
		self._row()
		self.settings.save()

	def test_an_unknown_provider_is_refused(self):
		self._row(provider="Nobody")
		self.assertRaises(frappe.ValidationError, self.settings.save)

	def test_a_company_can_only_appear_once(self):
		self._row()
		self._row()
		self.assertRaises(frappe.ValidationError, self.settings.save)

	def test_extra_configuration_must_be_a_json_object(self):
		self._row(extra_config="{not json")
		self.assertRaises(frappe.ValidationError, self.settings.save)

		self.settings = self._fresh()
		self._row(extra_config="[1, 2]")
		self.assertRaises(frappe.ValidationError, self.settings.save)

	def test_a_provider_can_require_settings(self):
		self.register_demo()

		self._row(provider="Demo")
		self.assertRaises(frappe.ValidationError, self.settings.save)

		self.settings = self._fresh()
		self._row(provider="Demo", endpoint_url="https://asp.example", client_id="id", client_secret="secret")
		self.settings.save()

	def test_a_disabled_row_needs_nothing(self):
		self.register_demo()

		self._row(provider="Demo", enabled=0)
		self.settings.save()

	def test_the_client_is_built_from_the_row_and_the_stored_secret(self):
		self.register_demo()

		self._row(
			provider="Demo",
			endpoint_url="https://asp.example",
			client_id="id",
			client_secret="s3cret",
			extra_config=json.dumps({"region": "ae"}),
		)
		self.settings.save()
		frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")

		client = registry.get_client(self.company)

		self.assertIsInstance(client, DemoASP)
		self.assertEqual(client.config.endpoint_url, "https://asp.example")
		self.assertEqual(client.config.client_secret, "s3cret")
		self.assertEqual(client.config.extra, {"region": "ae"})

	def test_no_client_for_a_company_that_is_not_enabled(self):
		self.settings.save()
		frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")
		self.assertRaises(frappe.ValidationError, registry.get_client, self.company)
