import frappe
from frappe.utils import flt

from uae_compliance.uae_compliance.constants import (
	ADJUSTMENT_ANNUAL_APPORTIONMENT,
	ADJUSTMENT_BAD_DEBT_RELIEF,
	ADJUSTMENT_BAD_DEBT_REPAYMENT,
	ADJUSTMENT_CAPITAL_ASSETS,
	ADJUSTMENT_IMPORT,
)
from uae_compliance.uae_compliance.constants.vat_return import EMIRATE_BOX_CODES

EXPENSE_ADJUSTMENTS = (
	ADJUSTMENT_BAD_DEBT_REPAYMENT,
	ADJUSTMENT_ANNUAL_APPORTIONMENT,
	ADJUSTMENT_CAPITAL_ASSETS,
)


def get_adjustments(companies: list[str], from_date, to_date) -> dict:
	"""The submitted UAE VAT Adjustments of the period, placed where the VAT 201 reports them:
	bad debt relief in the adjustment column of the emirate's box 1, bad debt repayment, annual
	apportionment and capital assets adjustments in the adjustment column of box 9, and import
	adjustments in the amount and VAT columns of box 7. All are signed: negative reduces."""
	rows = frappe.get_all(
		"UAE VAT Adjustment",
		filters={
			"company": ["in", companies],
			"docstatus": 1,
			"posting_date": ["between", [from_date, to_date]],
		},
		fields=["adjustment_type", "emirate", "amount", "vat_amount", "recoverable_percentage"],
	)

	by_emirate = dict.fromkeys(EMIRATE_BOX_CODES.values(), 0.0)
	expenses = 0.0
	import_amount = import_vat = recoverable_amount = recoverable_vat = 0.0
	for row in rows:
		if row.adjustment_type == ADJUSTMENT_BAD_DEBT_RELIEF and row.emirate in EMIRATE_BOX_CODES:
			by_emirate[EMIRATE_BOX_CODES[row.emirate]] += flt(row.vat_amount)
		elif row.adjustment_type in EXPENSE_ADJUSTMENTS:
			expenses += flt(row.vat_amount)
		elif row.adjustment_type == ADJUSTMENT_IMPORT:
			import_amount += flt(row.amount)
			import_vat += flt(row.vat_amount)
			share = flt(row.recoverable_percentage) / 100
			recoverable_amount += flt(row.amount) * share
			recoverable_vat += flt(row.vat_amount) * share

	return {
		"by_emirate": by_emirate,
		"expenses": expenses,
		"imports": {"amount": import_amount, "vat_amount": import_vat, "adjustment": 0.0},
		"imports_recoverable": {"amount": recoverable_amount, "vat_amount": recoverable_vat},
	}
