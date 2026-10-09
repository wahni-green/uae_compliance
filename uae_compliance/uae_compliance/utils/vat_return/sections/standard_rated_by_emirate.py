from frappe import _

from uae_compliance.uae_compliance.constants.vat_return import EMIRATE_BOX_CODES
from uae_compliance.uae_compliance.utils.vat_return import get_invoice_rows, summarize_box


def get_standard_rated_by_emirate(company: str, from_date, to_date, rows: list | None = None) -> dict:
	"""Boxes 1a-1g: standard rated supplies per emirate, keyed by box code. Each supply is reported
	in the emirate of the supplier's establishment most closely connected to it, which is the
	invoice's VAT Emirate. Invoices without one cannot be placed, so they are refused loudly."""
	if rows is None:
		rows = get_invoice_rows("Sales Invoice", company, from_date, to_date)

	standard = [row for row in rows if row.category == "Standard Rated"]
	_validate_emirates(standard)

	return {
		box_code: summarize_box([row for row in standard if row.uae_emirate == emirate])
		for emirate, box_code in EMIRATE_BOX_CODES.items()
	}


def _validate_emirates(rows: list) -> None:
	import frappe

	missing = sorted({row.invoice for row in rows if row.uae_emirate not in EMIRATE_BOX_CODES})
	if missing:
		frappe.throw(
			_(
				"Standard rated invoices without a VAT Emirate cannot be placed in boxes 1a-1g: {0}. Set"
				" the VAT Emirate on each of them."
			).format(", ".join(missing[:10]) + (" ..." if len(missing) > 10 else "")),
			title=_("VAT Emirate Missing"),
		)
