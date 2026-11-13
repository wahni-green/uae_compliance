from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.uae_compliance.utils.rounding import warn_if_not_commercial_rounding


class TestRoundingWarning(FrappeTestCase):
	def warns_with(self, method) -> bool:
		self.addCleanup(self.set_method, frappe.db.get_single_value("System Settings", "rounding_method"))
		self.set_method(method)
		with patch("uae_compliance.uae_compliance.utils.rounding.frappe.msgprint") as msgprint:
			warn_if_not_commercial_rounding()

		return msgprint.called

	def set_method(self, method):
		frappe.db.set_single_value("System Settings", "rounding_method", method)

	def test_bankers_rounding_is_warned_about(self):
		self.assertTrue(self.warns_with("Banker's Rounding"))
		self.assertTrue(self.warns_with("Banker's Rounding (legacy)"))

	def test_commercial_rounding_is_not(self):
		self.assertFalse(self.warns_with("Commercial Rounding"))
