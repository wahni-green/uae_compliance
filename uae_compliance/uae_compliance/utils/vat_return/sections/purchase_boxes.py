from frappe.utils import flt

from uae_compliance.uae_compliance.constants import ATTRIBUTION_EXEMPT, ATTRIBUTION_RESIDUAL
from uae_compliance.uae_compliance.utils.vat_return import get_invoice_rows, summarize_box

REVERSE_CHARGE = "reverse_charge"
POSTPONED_IMPORT = "postponed_import"
ORDINARY = "ordinary"


def classify_purchase_row(row) -> str | None:
	"""Which part of the return a purchase row belongs to, or None when it is not reported.

	Only Standard Rated rows are reported. Imports of goods with postponed VAT are declared in box 6;
	other reverse charge purchases in box 3. Imports that paid VAT at the border are ordinary
	purchases, because that VAT is not declared on the return. Rows flagged as non-recoverable input
	tax, or attributed to exempt supplies, are not reported as expenses at all."""
	if row.category != "Standard Rated":
		return None

	if row.uae_is_import_of_goods and row.uae_is_postponed_import_vat:
		return POSTPONED_IMPORT

	if row.uae_is_reverse_charge and not row.uae_is_import_of_goods:
		return REVERSE_CHARGE

	if row.uae_input_tax_not_recoverable or row.uae_input_tax_attribution == ATTRIBUTION_EXEMPT:
		return None

	return ORDINARY


def get_recoverable_vat(row, recovery_ratio: float = 100) -> float:
	"""The recoverable share of a row's input VAT: all of it, none of it (blocked input tax, or
	attributed to exempt supplies), or the period's recovery ratio (residual input tax)."""
	if row.uae_input_tax_not_recoverable or row.uae_input_tax_attribution == ATTRIBUTION_EXEMPT:
		return 0.0

	vat = flt(row.input_vat_amount)
	if row.uae_input_tax_attribution == ATTRIBUTION_RESIDUAL:
		return vat * flt(recovery_ratio) / 100

	return vat


def get_purchase_boxes(
	company: str, from_date, to_date, rows: list | None = None, recovery_ratio: float = 100
) -> dict:
	"""Boxes 3, 6, 9 and 10 from Purchase Invoice rows, plus the residual input VAT figures needed
	for the annual apportionment.

	The recoverable VAT is what was posted to the Input VAT account, reduced for rows attributed to
	exempt supplies or to residual input tax; the VAT due is what was posted to the Output VAT
	account (the self-accounted liability). Box 10 recovers the VAT declared in boxes 3 and 6."""
	if rows is None:
		rows = get_invoice_rows("Purchase Invoice", company, from_date, to_date)

	buckets: dict[str, list] = {REVERSE_CHARGE: [], POSTPONED_IMPORT: [], ORDINARY: []}
	for row in rows:
		bucket = classify_purchase_row(row)
		if bucket:
			buckets[bucket].append(row)

	def recoverable_box(selected: list) -> dict:
		box = summarize_box(selected, "input_vat_amount")
		box["vat_amount"] = sum(get_recoverable_vat(row, recovery_ratio) for row in selected)
		return box

	# Rows that claim nothing (attributed to exempt supplies, or blocked input tax) keep their VAT due
	# in boxes 3 and 6 but are left out of box 10.
	claimable = [
		row
		for row in buckets[REVERSE_CHARGE] + buckets[POSTPONED_IMPORT]
		if row.uae_input_tax_attribution != ATTRIBUTION_EXEMPT and not row.uae_input_tax_not_recoverable
	]

	residual = [
		row for row in buckets[ORDINARY] + claimable if row.uae_input_tax_attribution == ATTRIBUTION_RESIDUAL
	]

	return {
		"reverse_charge_supplies": summarize_box(buckets[REVERSE_CHARGE], "output_vat_amount"),
		"imports": summarize_box(buckets[POSTPONED_IMPORT], "output_vat_amount"),
		"standard_rated_expenses": recoverable_box(buckets[ORDINARY]),
		"reverse_charge_expenses": recoverable_box(claimable),
		"residual_input_vat": sum(flt(row.input_vat_amount) for row in residual),
		"residual_recoverable_vat": sum(get_recoverable_vat(row, recovery_ratio) for row in residual),
	}
