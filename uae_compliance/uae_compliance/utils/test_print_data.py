import datetime

import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.uae_compliance.utils.print_data import get_issue_order


class TestIssueOrder(FrappeTestCase):
	def test_times_are_compared_as_times_not_strings(self):
		"""'9:00:00' sorts after '10:00:00' as text, which is what a database timedelta prints as."""
		nine = frappe._dict(
			posting_date="2026-03-01",
			posting_time=datetime.timedelta(hours=9),
			creation="2026-03-01 08:00:00",
		)
		ten = frappe._dict(posting_date="2026-03-01", posting_time="10:00:00", creation="2026-03-01 08:00:00")

		self.assertLess(get_issue_order(nine), get_issue_order(ten))

	def test_date_dominates_time(self):
		earlier = frappe._dict(
			posting_date="2026-03-01", posting_time="23:00:00", creation="2026-03-01 08:00:00"
		)
		later = frappe._dict(
			posting_date="2026-03-02", posting_time="01:00:00", creation="2026-03-01 08:00:00"
		)

		self.assertLess(get_issue_order(earlier), get_issue_order(later))

	def test_creation_breaks_ties(self):
		first = frappe._dict(
			posting_date="2026-03-01", posting_time="10:00:00", creation="2026-03-01 08:00:00"
		)
		second = frappe._dict(
			posting_date="2026-03-01", posting_time="10:00:00", creation="2026-03-01 08:00:01"
		)

		self.assertLess(get_issue_order(first), get_issue_order(second))
