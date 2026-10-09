import frappe
from frappe.utils import flt

from uae_compliance.uae_compliance.constants import (
	ADJUSTMENT_ANNUAL_APPORTIONMENT,
	ADJUSTMENT_BAD_DEBT_RELIEF,
	ADJUSTMENT_BAD_DEBT_REPAYMENT,
	ADJUSTMENT_CAPITAL_ASSETS,
	ADJUSTMENT_IMPORT,
	ATTRIBUTION_EXEMPT,
	ATTRIBUTION_RESIDUAL,
)
from uae_compliance.uae_compliance.constants.vat_return import EMIRATE_BOX_CODES
from uae_compliance.uae_compliance.utils.vat_return.group import get_internal_parties

EXPENSE_ADJUSTMENTS = (
	ADJUSTMENT_BAD_DEBT_REPAYMENT,
	ADJUSTMENT_ANNUAL_APPORTIONMENT,
	ADJUSTMENT_CAPITAL_ASSETS,
)


def get_adjustments(companies: list[str], from_date, to_date, recovery_ratio: float = 100) -> dict:
	"""The submitted UAE VAT Adjustments of the period, placed where the VAT 201 reports them:
	bad debt relief in the adjustment column of the emirate's box 1, bad debt repayment, annual
	apportionment and capital assets adjustments in the adjustment column of box 9, and import
	adjustments in the amount and VAT columns of box 7. All are signed: negative reduces.

	The recoverable share of an import adjustment is also recovered in box 10: all of it, none of it
	(attributed to exempt supplies) or the period's recovery ratio (residual input tax, which the
	annual apportionment then trues up)."""
	rows = frappe.get_all(
		"UAE VAT Adjustment",
		filters={
			"company": ["in", companies],
			"docstatus": 1,
			"posting_date": ["between", [from_date, to_date]],
		},
		fields=[
			"adjustment_type",
			"emirate",
			"amount",
			"vat_amount",
			"input_tax_attribution",
			"sales_invoice",
			"purchase_invoice",
		],
	)
	rows = _without_intra_group_bad_debt(rows, companies)

	by_emirate = dict.fromkeys(EMIRATE_BOX_CODES.values(), 0.0)
	expenses = 0.0
	import_amount = import_vat = recoverable_amount = recoverable_vat = 0.0
	residual_vat = residual_recovered = 0.0
	for row in rows:
		if row.adjustment_type == ADJUSTMENT_BAD_DEBT_RELIEF and row.emirate in EMIRATE_BOX_CODES:
			by_emirate[EMIRATE_BOX_CODES[row.emirate]] += flt(row.vat_amount)
		elif row.adjustment_type in EXPENSE_ADJUSTMENTS:
			expenses += flt(row.vat_amount)
		elif row.adjustment_type == ADJUSTMENT_IMPORT:
			import_amount += flt(row.amount)
			import_vat += flt(row.vat_amount)

			if row.input_tax_attribution == ATTRIBUTION_EXEMPT:
				share = 0.0
			elif row.input_tax_attribution == ATTRIBUTION_RESIDUAL:
				share = flt(recovery_ratio) / 100
				residual_vat += flt(row.vat_amount)
				residual_recovered += flt(row.vat_amount) * share
			else:
				share = 1.0

			recoverable_amount += flt(row.amount) * share
			recoverable_vat += flt(row.vat_amount) * share

	return {
		"by_emirate": by_emirate,
		"expenses": expenses,
		"imports": {"amount": import_amount, "vat_amount": import_vat, "adjustment": 0.0},
		"imports_recoverable": {"amount": recoverable_amount, "vat_amount": recoverable_vat},
		"residual_input_vat": residual_vat,
		"residual_recoverable_vat": residual_recovered,
	}


def _without_intra_group_bad_debt(rows: list, companies: list[str]) -> list:
	"""Supplies between the members of a tax group are disregarded, so the bad debt relief or
	repayment of such a supply has nothing to adjust."""
	if len(companies) < 2:
		return rows

	customers = get_internal_parties("Customer", companies)
	suppliers = get_internal_parties("Supplier", companies)

	def is_internal(row) -> bool:
		if row.sales_invoice:
			return frappe.db.get_value("Sales Invoice", row.sales_invoice, "customer") in customers
		if row.purchase_invoice:
			return frappe.db.get_value("Purchase Invoice", row.purchase_invoice, "supplier") in suppliers

		return False

	return [row for row in rows if not is_internal(row)]
