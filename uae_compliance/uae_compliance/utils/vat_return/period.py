import frappe
from frappe import _
from frappe.utils import add_days, add_months, get_first_day, get_last_day, getdate

from uae_compliance.uae_compliance.constants.vat_return import (
	MONTHLY,
	RETURN_DUE_DAYS,
	STAGGER_START_MONTHS,
)


def get_period_type(from_date, to_date) -> str:
	"""Monthly or Quarterly when the dates span exactly that many whole calendar months, else
	Custom. The FTA can assign other periods (for example a first period that starts on the
	registration date), so Custom is allowed."""
	from_date, to_date = getdate(from_date), getdate(to_date)
	if from_date != get_first_day(from_date) or to_date != get_last_day(to_date):
		return "Custom"

	if to_date == get_last_day(from_date):
		return "Monthly"

	if to_date == get_last_day(add_months(from_date, 2)):
		return "Quarterly"

	return "Custom"


def get_period_warning(from_date, to_date, filing_frequency: str | None) -> str | None:
	"""A message when the period does not match the company's configured filing frequency."""
	if not filing_frequency:
		return None

	period_type = get_period_type(from_date, to_date)
	if filing_frequency == MONTHLY:
		return (
			None
			if period_type == "Monthly"
			else _("The company files monthly, but this period is not one calendar month.")
		)

	if period_type == "Quarterly" and getdate(from_date).month in STAGGER_START_MONTHS.get(
		filing_frequency, ()
	):
		return None

	return _("This period does not match the company's filing frequency ({0}).").format(filing_frequency)


def get_due_date(to_date):
	"""The 28th day after the period ends, moved to the next business day if it falls on a weekend.
	Public holidays are not considered."""
	due = add_days(getdate(to_date), RETURN_DUE_DAYS)
	weekday = due.weekday()  # Saturday 5, Sunday 6
	if weekday == 5:
		return add_days(due, 2)
	if weekday == 6:
		return add_days(due, 1)

	return due


def get_filing_frequency(company: str) -> str | None:
	settings = frappe.get_cached_doc("UAE Compliance Settings")
	for row in settings.vat_accounts:
		if row.company == company:
			return row.filing_frequency

	return None
