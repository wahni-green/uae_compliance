from uae_compliance.uae_compliance.constants.vat_return import BOX_EXEMPT, BOX_ZERO_RATED
from uae_compliance.uae_compliance.utils.vat_return import get_invoice_rows, summarize_box

SALES_BOX_BY_CATEGORY = {"Zero Rated": BOX_ZERO_RATED, "Exempt": BOX_EXEMPT}


def get_sales_boxes(company: str, from_date, to_date, rows: list | None = None) -> dict:
	"""Boxes 2, 4 and 5. Box 4 (zero rated) and 5 (exempt) take an amount only and include exports.
	Box 2 reports tax refunded to tourists, which reduces the VAT due and is reported as a negative
	VAT amount; its amount column is left at zero because the refunded value is not recorded."""
	if rows is None:
		rows = get_invoice_rows("Sales Invoice", company, from_date, to_date)

	invoices = {row.invoice: row for row in rows}
	tourist_refund = sum(abs(invoice.uae_tourist_refund or 0) for invoice in invoices.values())

	return {
		"tourist_refunds": {"amount": 0.0, "vat_amount": -tourist_refund, "adjustment": 0.0},
		"zero_rated": summarize_box([row for row in rows if row.category == "Zero Rated"]),
		"exempt": summarize_box([row for row in rows if row.category == "Exempt"]),
	}
