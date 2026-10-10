import math

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate

from uae_compliance.uae_compliance.constants.vat_return import REVERSE_CHARGE_SUPPLY_CATEGORY


def get_recovery_ratio(taxable_supplies: float, exempt_supplies: float) -> int:
	"""The share of residual input VAT that can be recovered: taxable supplies (standard and zero
	rated) over all supplies, as a whole percentage rounded to the nearest whole number (ER Art 55).
	A period with no supplies recovers everything."""
	total = flt(taxable_supplies) + flt(exempt_supplies)
	if total <= 0:
		return 100

	ratio = math.floor(flt(taxable_supplies) / total * 100 + 0.5)
	return max(0, min(100, ratio))


def get_period_supplies(sales_rows: list) -> tuple[float, float]:
	"""(taxable, exempt) supplies of a set of sales rows. Credit notes net in already."""
	taxable = sum(
		flt(row.base_net_amount)
		for row in sales_rows
		# A sale under the reverse charge is a taxable supply for the recovery ratio, although the
		# supplier does not report it in a box.
		if row.category in ("Standard Rated", "Zero Rated", REVERSE_CHARGE_SUPPLY_CATEGORY)
	)
	exempt = sum(flt(row.base_net_amount) for row in sales_rows if row.category == "Exempt")
	return taxable, exempt


def get_annual_apportionment(company: str, from_date, to_date) -> dict:
	"""The true-up of residual input VAT for a tax year, from the company's Filed returns in it. The
	annual ratio is applied to the year's total residual input VAT, and the difference from what the
	periods recovered is the adjustment, to be reported in the first return of the next tax year.

	The year has to be complete: its Filed returns must run without a gap from the first day to the
	last, and each must have recorded its partial exemption figures."""
	frappe.has_permission("Company", "read", doc=company, throw=True)

	returns = frappe.get_all(
		"UAE VAT Return",
		filters={
			"company": company,
			"status": "Filed",
			"from_date": [">=", from_date],
			"to_date": ["<=", to_date],
		},
		fields=[
			"name",
			"from_date",
			"to_date",
			"apportionment_recorded",
			"taxable_supplies_value",
			"exempt_supplies_value",
			"residual_input_vat",
			"residual_recoverable_vat",
		],
		order_by="from_date, to_date",
	)
	if not returns:
		frappe.throw(
			_("There are no Filed returns for {0} between {1} and {2}.").format(company, from_date, to_date),
			title=_("No Returns"),
		)

	unrecorded = [r.name for r in returns if not r.apportionment_recorded]
	if unrecorded:
		frappe.throw(
			_(
				"These returns were filed before their partial exemption figures were recorded, so the year cannot be calculated: {0}."
			).format(", ".join(unrecorded)),
			title=_("Figures Not Recorded"),
		)

	_validate_year_is_covered(returns, from_date, to_date)

	taxable = sum(flt(r.taxable_supplies_value) for r in returns)
	exempt = sum(flt(r.exempt_supplies_value) for r in returns)
	residual = sum(flt(r.residual_input_vat) for r in returns)
	claimed = sum(flt(r.residual_recoverable_vat) for r in returns)

	annual_ratio = get_recovery_ratio(taxable, exempt)
	annual_recoverable = flt(residual * annual_ratio / 100, 2)

	return {
		"returns": len(returns),
		"annual_ratio": annual_ratio,
		"residual_input_vat": flt(residual, 2),
		"annual_recoverable": annual_recoverable,
		"claimed": flt(claimed, 2),
		"adjustment": flt(annual_recoverable - claimed, 2),
	}


def _validate_year_is_covered(returns: list, from_date, to_date) -> None:
	"""The returns have to cover every day of the tax year, or the annual figures are incomplete."""
	expected = getdate(from_date)
	for row in returns:
		if getdate(row.from_date) > expected:
			frappe.throw(
				_("The Filed returns leave a gap from {0}. File every return of the tax year first.").format(
					frappe.format(expected, {"fieldtype": "Date"})
				),
				title=_("Incomplete Tax Year"),
			)

		expected = max(expected, add_days(getdate(row.to_date), 1))

	if expected <= getdate(to_date):
		frappe.throw(
			_("The Filed returns end before {0}. File every return of the tax year first.").format(
				frappe.format(to_date, {"fieldtype": "Date"})
			),
			title=_("Incomplete Tax Year"),
		)
