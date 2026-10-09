from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from uae_compliance.uae_compliance.utils.company import is_uae_company


class TestIsUAECompany(FrappeTestCase):
	def test_blank_company_is_not_uae(self):
		self.assertFalse(is_uae_company(None))
		self.assertFalse(is_uae_company(""))

	def test_country_gate(self):
		with patch("frappe.get_cached_value", return_value="United Arab Emirates"):
			self.assertTrue(is_uae_company("X"))
		with patch("frappe.get_cached_value", return_value="Oman"):
			self.assertFalse(is_uae_company("X"))
