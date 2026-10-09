import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.uae_compliance.constants.excise_rates import EXCISE_RATES
from uae_compliance.uae_compliance.setup import create_excise_rates


class TestUAEExciseRate(FrappeTestCase):
	def test_seed_is_idempotent_and_never_overwrites(self):
		create_excise_rates()
		name = EXCISE_RATES[0]["category"]
		frappe.db.set_value("UAE Excise Rate", name, "rate", 99)

		create_excise_rates()

		self.assertEqual(frappe.db.get_value("UAE Excise Rate", name, "rate"), 99)
		self.assertEqual(frappe.db.count("UAE Excise Rate", {"category": name}), 1)

	def test_current_rates(self):
		create_excise_rates()
		rates = {
			rate.category: (rate.rate_type, rate.rate)
			for rate in frappe.get_all("UAE Excise Rate", fields=["category", "rate_type", "rate"])
		}

		self.assertEqual(rates["Tobacco and Tobacco Products"], ("Percentage of Excise Price", 100))
		self.assertEqual(rates["Energy Drinks"], ("Percentage of Excise Price", 100))
		self.assertEqual(rates["Sweetened Drinks (8 g or more sugar per 100 ml)"], ("Per Litre", 1.09))
		self.assertEqual(rates["Sweetened Drinks (5 g to under 8 g sugar per 100 ml)"], ("Per Litre", 0.79))

	def test_the_repealed_fifty_percent_rate_is_not_seeded(self):
		create_excise_rates()
		self.assertFalse(
			frappe.db.exists("UAE Excise Rate", {"rate_type": "Percentage of Excise Price", "rate": 50})
		)
