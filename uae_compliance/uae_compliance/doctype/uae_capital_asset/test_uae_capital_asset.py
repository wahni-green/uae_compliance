import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import get_uae_test_company

# Test records for Sales and Purchase Invoice pull in every linked doctype recursively, including
# ones that are not installed; these tests build the invoices they need themselves.
test_ignore = ["Sales Invoice", "Purchase Invoice"]


class TestUAECapitalAsset(FrappeTestCase):
	def _asset(self, **kwargs):
		return frappe.get_doc(
			{
				"doctype": "UAE Capital Asset",
				"company": get_uae_test_company(),
				"asset_name": "Head Office Tower",
				"asset_type": "Building",
				"first_use_date": "2026-01-01",
				"cost": 6_000_000,
				"input_vat": 300_000,
				"initial_recoverable_percentage": 80,
				**kwargs,
			}
		)

	def test_buildings_adjust_over_ten_years_and_other_assets_over_five(self):
		building = self._asset().insert()
		self.assertEqual((building.adjustment_years, len(building.adjustments)), (10, 10))
		self.assertEqual(building.annual_input_vat, 30_000)

		other = self._asset(asset_type="Other").insert()
		self.assertEqual((other.adjustment_years, len(other.adjustments)), (5, 5))
		self.assertEqual(other.annual_input_vat, 60_000)

	def test_below_the_threshold_is_rejected(self):
		self.assertRaises(frappe.ValidationError, self._asset(cost=4_999_999).insert)

	def test_adjustment_follows_the_change_in_recoverable_percentage(self):
		asset = self._asset(asset_type="Other").insert()
		asset.adjustments[1].recoverable_percentage = 60  # -20 points
		asset.adjustments[2].recoverable_percentage = 100  # +20 points
		asset.save()

		self.assertEqual(asset.adjustments[0].adjustment_vat, 0)
		self.assertEqual(asset.adjustments[1].adjustment_vat, -12_000)
		self.assertEqual(asset.adjustments[2].adjustment_vat, 12_000)

	def test_year_ends_count_from_first_use(self):
		asset = self._asset().insert()
		self.assertEqual(str(asset.adjustments[0].tax_year_end), "2027-01-01")
		self.assertEqual(str(asset.adjustments[9].tax_year_end), "2036-01-01")

	def test_saving_again_keeps_what_was_entered(self):
		asset = self._asset(asset_type="Other").insert()
		asset.adjustments[3].recoverable_percentage = 50
		asset.save()
		asset.save()

		self.assertEqual(asset.adjustments[3].recoverable_percentage, 50)

	def test_creates_a_draft_adjustment_once(self):
		asset = self._asset(asset_type="Other").insert()
		asset.adjustments[1].recoverable_percentage = 60
		asset.adjustments[1].adjustment_date = "2027-03-01"
		asset.save()

		name = asset.create_adjustment(asset.adjustments[1].name)
		adjustment = frappe.get_doc("UAE VAT Adjustment", name)
		self.assertEqual(
			(adjustment.adjustment_type, adjustment.vat_amount, adjustment.docstatus),
			("Capital Assets Scheme", -12_000, 0),
		)

		asset.reload()
		self.assertEqual(asset.adjustments[1].vat_adjustment, name)
		self.assertRaises(frappe.ValidationError, asset.create_adjustment, asset.adjustments[1].name)

	def test_no_adjustment_to_create_when_nothing_changed(self):
		asset = self._asset(asset_type="Other").insert()
		asset.adjustments[1].adjustment_date = "2027-03-01"
		asset.save()

		self.assertRaises(frappe.ValidationError, asset.create_adjustment, asset.adjustments[1].name)
