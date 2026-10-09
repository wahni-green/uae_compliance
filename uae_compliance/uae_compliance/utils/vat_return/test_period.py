from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from uae_compliance.uae_compliance.utils.vat_return.period import (
	get_due_date,
	get_period_type,
	get_period_warning,
)


class TestPeriod(FrappeTestCase):
	def test_period_type(self):
		self.assertEqual(get_period_type("2026-03-01", "2026-03-31"), "Monthly")
		self.assertEqual(get_period_type("2026-02-01", "2026-04-30"), "Quarterly")
		self.assertEqual(get_period_type("2026-03-15", "2026-04-30"), "Custom")
		self.assertEqual(get_period_type("2026-01-01", "2026-05-31"), "Custom")

	def test_monthly_company_warns_about_a_quarter(self):
		self.assertIsNone(get_period_warning("2026-03-01", "2026-03-31", "Monthly"))
		self.assertTrue(get_period_warning("2026-02-01", "2026-04-30", "Monthly"))

	def test_stagger_periods(self):
		stagger_1 = "Quarterly - Stagger 1 (Feb-Apr)"
		self.assertIsNone(get_period_warning("2026-02-01", "2026-04-30", stagger_1))
		self.assertIsNone(get_period_warning("2026-11-01", "2027-01-31", stagger_1))
		self.assertTrue(get_period_warning("2026-01-01", "2026-03-31", stagger_1))

		stagger_3 = "Quarterly - Stagger 3 (Apr-Jun)"
		self.assertIsNone(get_period_warning("2026-01-01", "2026-03-31", stagger_3))
		self.assertIsNone(get_period_warning("2026-10-01", "2026-12-31", stagger_3))

	def test_no_warning_without_a_frequency(self):
		self.assertIsNone(get_period_warning("2026-03-15", "2026-04-30", None))

	def test_due_date_is_28_days_after_period_end(self):
		# 31 Mar 2026 + 28 days = Tue 28 Apr 2026
		self.assertEqual(get_due_date("2026-03-31"), getdate("2026-04-28"))

	def test_due_date_rolls_past_the_weekend(self):
		# 31 Jul 2026 + 28 days = Fri 28 Aug 2026 (no roll); 30 Jun 2026 + 28 = Tue 28 Jul
		self.assertEqual(get_due_date("2026-07-31"), getdate("2026-08-28"))
		# 31 Oct 2026 + 28 = Sat 28 Nov 2026 -> Mon 30 Nov
		self.assertEqual(get_due_date("2026-10-31"), getdate("2026-11-30"))
		# 30 Apr 2026 + 28 = Thu 28 May; 31 May 2026 + 28 = Sun 28 Jun -> Mon 29 Jun
		self.assertEqual(get_due_date("2026-05-31"), getdate("2026-06-29"))
