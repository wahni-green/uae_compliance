import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import make_address


class TestAddressEmirate(FrappeTestCase):
	def test_a_uae_address_needs_an_emirate(self):
		with self.assertRaises(frappe.ValidationError):
			make_address("_Test No Emirate", "United Arab Emirates")

	def test_a_uae_address_with_an_emirate_is_saved(self):
		make_address("_Test With Emirate", "United Arab Emirates", uae_emirate="Dubai")

	def test_an_address_abroad_needs_no_emirate(self):
		make_address("_Test Abroad", "India")
