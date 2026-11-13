import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.uae_compliance.constants.pint_ae import EXEMPTION_REASONS
from uae_compliance.uae_compliance.setup import create_exemption_reasons


class TestUAEExemptionReason(FrappeTestCase):
	def test_seed_is_idempotent_and_never_overwrites(self):
		create_exemption_reasons()
		code = next(iter(EXEMPTION_REASONS))
		frappe.db.set_value("UAE Exemption Reason", code, "description", "edited by finance")

		create_exemption_reasons()

		self.assertEqual(
			frappe.db.get_value("UAE Exemption Reason", code, "description"), "edited by finance"
		)
		self.assertEqual(frappe.db.count("UAE Exemption Reason", {"reason_code": code}), 1)
