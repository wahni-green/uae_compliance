from uae_compliance.uae_compliance.utils.vat_return import get_invoice_rows, summarize_box

REVERSE_CHARGE = "reverse_charge"
POSTPONED_IMPORT = "postponed_import"
ORDINARY = "ordinary"


def classify_purchase_row(row) -> str | None:
	"""Which part of the return a purchase row belongs to, or None when it is not reported.

	Only Standard Rated rows are reported. Imports of goods with postponed VAT are declared in box 6;
	other reverse charge purchases in box 3. Imports that paid VAT at the border are ordinary
	purchases, because that VAT is not declared on the return. Rows flagged as non-recoverable input
	tax are not reported at all."""
	if row.category != "Standard Rated":
		return None

	if row.uae_is_import_of_goods and row.uae_is_postponed_import_vat:
		return POSTPONED_IMPORT

	if row.uae_is_reverse_charge and not row.uae_is_import_of_goods:
		return REVERSE_CHARGE

	if row.uae_input_tax_not_recoverable:
		return None

	return ORDINARY


def get_purchase_boxes(company: str, from_date, to_date, rows: list | None = None) -> dict:
	"""Boxes 3, 6, 9 and 10 from Purchase Invoice rows.

	The recoverable VAT is what was posted to the Input VAT account; the VAT due is what was posted
	to the Output VAT account (the self-accounted liability). Box 10 recovers the VAT declared in
	boxes 3 and 6."""
	if rows is None:
		rows = get_invoice_rows("Purchase Invoice", company, from_date, to_date)

	buckets: dict[str, list] = {REVERSE_CHARGE: [], POSTPONED_IMPORT: [], ORDINARY: []}
	for row in rows:
		bucket = classify_purchase_row(row)
		if bucket:
			buckets[bucket].append(row)

	return {
		"reverse_charge_supplies": summarize_box(buckets[REVERSE_CHARGE], "output_vat_amount"),
		"imports": summarize_box(buckets[POSTPONED_IMPORT], "output_vat_amount"),
		"standard_rated_expenses": summarize_box(buckets[ORDINARY], "input_vat_amount"),
		# Rows flagged as non-recoverable input tax keep their VAT due in boxes 3 and 6 but recover
		# nothing in box 10.
		"reverse_charge_expenses": summarize_box(
			[
				row
				for row in buckets[REVERSE_CHARGE] + buckets[POSTPONED_IMPORT]
				if not row.uae_input_tax_not_recoverable
			],
			"input_vat_amount",
		),
	}
