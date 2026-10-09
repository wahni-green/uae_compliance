from frappe.utils import flt

from uae_compliance.uae_compliance.constants.vat_return import BOX_EXEMPT, BOX_ZERO_RATED
from uae_compliance.uae_compliance.utils.vat_return import get_invoice_rows, summarize_box

SALES_BOX_BY_CATEGORY = {"Zero Rated": BOX_ZERO_RATED, "Exempt": BOX_EXEMPT}


def get_tourist_refunds_by_invoice(rows: list) -> dict[str, float]:
	"""The tax refunded to tourists per invoice, in company currency. The refund is recorded in the
	invoice's currency, so it is converted at the invoice's rate. Each invoice counts once however
	many rows it has."""
	invoices = {row.invoice: row for row in rows}
	return {
		name: abs(flt(invoice.uae_tourist_refund)) * (flt(invoice.conversion_rate) or 1)
		for name, invoice in invoices.items()
		if flt(invoice.uae_tourist_refund)
	}


def get_tourist_refund(rows: list) -> float:
	"""The total tax refunded to tourists on the rows' invoices, in company currency."""
	return sum(get_tourist_refunds_by_invoice(rows).values())


def get_margin_scheme(rows: list) -> dict:
	"""Whether the profit margin scheme was used in the period and the purchase price of the goods
	sold under it, which the return reports as a standard rated expense in box 9."""
	margin_rows = [row for row in rows if row.get("uae_is_margin_scheme")]
	return {
		"applied": bool(margin_rows),
		"purchase_price": sum(flt(row.margin_purchase_price) for row in margin_rows),
	}


def get_sales_boxes(company: str, from_date, to_date, rows: list | None = None) -> dict:
	"""Boxes 2, 4 and 5. Box 4 (zero rated) and 5 (exempt) take an amount only and include exports.
	Box 2 reports tax refunded to tourists, which reduces the VAT due and is reported as a negative
	VAT amount; its amount column is left at zero because the refunded value is not recorded."""
	if rows is None:
		rows = get_invoice_rows("Sales Invoice", company, from_date, to_date)

	tourist_refund = get_tourist_refund(rows)

	return {
		"tourist_refunds": {"amount": 0.0, "vat_amount": -tourist_refund, "adjustment": 0.0},
		"zero_rated": summarize_box([row for row in rows if row.category == "Zero Rated"]),
		"exempt": summarize_box([row for row in rows if row.category == "Exempt"]),
	}
