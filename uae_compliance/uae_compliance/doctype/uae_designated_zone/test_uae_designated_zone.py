import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.uae_compliance.constants.designated_zones import DESIGNATED_ZONES
from uae_compliance.uae_compliance.setup import create_designated_zones


class TestUAEDesignatedZone(FrappeTestCase):
	def test_seed_is_idempotent_and_never_overwrites(self):
		create_designated_zones()
		name = DESIGNATED_ZONES[0]["zone_name"]
		frappe.db.set_value("UAE Designated Zone", name, "remarks", "edited by admin")

		create_designated_zones()

		self.assertEqual(frappe.db.get_value("UAE Designated Zone", name, "remarks"), "edited by admin")
		self.assertEqual(frappe.db.count("UAE Designated Zone", {"zone_name": name}), 1)

	def test_removed_zones_are_not_seeded(self):
		names = {zone["zone_name"] for zone in DESIGNATED_ZONES}
		self.assertNotIn("Dubai Textile City", names)
		self.assertNotIn("Al Quoz Free Zone", names)
