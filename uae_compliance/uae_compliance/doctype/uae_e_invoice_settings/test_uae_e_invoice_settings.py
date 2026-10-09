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


class DemoASP(ASPClient):
	name = "Demo"
	required_settings = ("endpoint_url", "client_id", "client_secret")

	def submit(self, document, idempotency_key):
		return SubmitResult("DEMO-1", "Submitted")

	def get_status(self, provider_reference):
		return StatusResult("Cleared")


class TestUAEEInvoiceSettings(FrappeTestCase):
	def setUp(self):
		self.company = get_uae_test_company()
		self.settings = self._fresh()

	def _fresh(self):
		settings = frappe.get_doc("UAE E-Invoice Settings")
		settings.companies = []
		return settings

	def _row(self, **values):
		self.settings.append(
			"companies",
			{"company": self.company, "enabled": 1, "provider": "Mock", "environment": "Sandbox", **values},
		)

	def test_the_mock_provider_is_always_available(self):
		self.assertIn("Mock", registry.get_provider_names())

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
		registry.register_provider(DemoASP)
		self.addCleanup(registry._PROVIDERS.pop, "Demo", None)

		self._row(provider="Demo")
		self.assertRaises(frappe.ValidationError, self.settings.save)

		self.settings = self._fresh()
		self._row(provider="Demo", endpoint_url="https://asp.example", client_id="id", client_secret="secret")
		self.settings.save()

	def test_a_disabled_row_needs_nothing(self):
		registry.register_provider(DemoASP)
		self.addCleanup(registry._PROVIDERS.pop, "Demo", None)

		self._row(provider="Demo", enabled=0)
		self.settings.save()

	def test_the_client_is_built_from_the_row_and_the_stored_secret(self):
		registry.register_provider(DemoASP)
		self.addCleanup(registry._PROVIDERS.pop, "Demo", None)

		self._row(
			provider="Demo",
			endpoint_url="https://asp.example",
			client_id="id",
			client_secret="s3cret",
			extra_config=json.dumps({"region": "ae"}),
		)
		self.settings.save()
		frappe.clear_document_cache("UAE E-Invoice Settings", "UAE E-Invoice Settings")

		client = registry.get_client(self.company)

		self.assertIsInstance(client, DemoASP)
		self.assertEqual(client.config.endpoint_url, "https://asp.example")
		self.assertEqual(client.config.client_secret, "s3cret")
		self.assertEqual(client.config.extra, {"region": "ae"})

	def test_no_client_for_a_company_that_is_not_enabled(self):
		self.settings.save()
		frappe.clear_document_cache("UAE E-Invoice Settings", "UAE E-Invoice Settings")
		self.assertRaises(frappe.ValidationError, registry.get_client, self.company)
