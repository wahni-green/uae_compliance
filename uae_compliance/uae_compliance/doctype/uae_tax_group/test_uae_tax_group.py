from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import delete_tax_groups, get_uae_test_company, make_uae_company


class TestUAETaxGroup(FrappeTestCase):
	def setUp(self):
		self.a = get_uae_test_company()
		self.b = make_uae_company("_Test UAE Group Member B", "TGB")

		# Tests in a class share one transaction, so groups must not outlive the test that made them.
		self.addCleanup(delete_tax_groups)

	def _group(self, **kwargs):
		return frappe.get_doc(
			{
				"doctype": "UAE Tax Group",
				"group_name": "_Test Tax Group",
				"representative_member": self.a,
				"members": [{"company": self.a}, {"company": self.b}],
				**kwargs,
			}
		)

	def test_membership_is_mirrored_on_the_companies(self):
		group = self._group().insert()

		self.assertEqual(frappe.db.get_value("Company", self.a, "uae_tax_group"), group.name)
		self.assertEqual(frappe.db.get_value("Company", self.b, "uae_tax_group"), group.name)

	def test_removing_a_member_clears_its_link(self):
		third = make_uae_company("_Test UAE Group Member C", "TGC")
		group = self._group(members=[{"company": self.a}, {"company": self.b}, {"company": third}]).insert()
		self.assertEqual(frappe.db.get_value("Company", third, "uae_tax_group"), group.name)

		group.members = [row for row in group.members if row.company != third]
		group.save()

		self.assertFalse(frappe.db.get_value("Company", third, "uae_tax_group"))
		self.assertEqual(frappe.db.get_value("Company", self.a, "uae_tax_group"), group.name)
		self.assertEqual(frappe.db.get_value("Company", self.b, "uae_tax_group"), group.name)

	def test_a_group_cannot_shrink_below_two_members(self):
		group = self._group().insert()
		group.members = [row for row in group.members if row.company == self.a]
		self.assertRaises(frappe.ValidationError, group.save)

	def test_member_companies_are_locked_in_a_fixed_order_before_the_check(self):
		real = frappe.db.get_value
		locked = []

		def spy(*args, **kwargs):
			if kwargs.get("for_update") and args[0] == "Company":
				locked.append(args[1])
			return real(*args, **kwargs)

		with patch.object(frappe.db, "get_value", side_effect=spy):
			self._group().insert()

		self.assertEqual(locked, sorted(locked))
		self.assertEqual(set(locked), {self.a, self.b})

	def test_deleting_the_group_clears_the_links(self):
		group = self._group().insert()
		group.delete()

		self.assertFalse(frappe.db.get_value("Company", self.a, "uae_tax_group"))
		self.assertFalse(frappe.db.get_value("Company", self.b, "uae_tax_group"))

	def test_needs_two_members(self):
		group = self._group(members=[{"company": self.a}])
		self.assertRaises(frappe.ValidationError, group.insert)

	def test_representative_must_be_a_member(self):
		other = make_uae_company("_Test UAE Group Member C", "TGC")
		group = self._group(representative_member=other)
		self.assertRaises(frappe.ValidationError, group.insert)

	def test_a_company_can_only_be_listed_once(self):
		group = self._group(members=[{"company": self.a}, {"company": self.a}])
		self.assertRaises(frappe.ValidationError, group.insert)

	def test_a_company_cannot_be_in_two_groups(self):
		self._group().insert()
		second = self._group(group_name="_Test Tax Group 2")
		self.assertRaises(frappe.ValidationError, second.insert)

	def test_members_must_be_uae_companies(self):
		india = frappe.db.get_value("Company", {"country": "India"})
		group = self._group(members=[{"company": self.a}, {"company": india}])
		self.assertRaises(frappe.ValidationError, group.insert)
