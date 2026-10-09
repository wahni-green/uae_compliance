import frappe
from frappe.utils import flt

from uae_compliance.uae_compliance.utils.tax_account import (
	get_item_wise_vat_rates,
	get_output_vat_account,
	is_output_vat_account,
)


def get_output_vat_amount(doc, base: bool = False) -> float | None:
	"""Sum of only the tax rows posted to the company's configured Output VAT account (not every
	charge: freight, discount, ... are not VAT). Document currency, or company currency (AED) if
	`base`. None, not 0, when no Output VAT account is configured, so print formats can warn
	instead of printing a misleading zero."""
	company = doc.get("company")
	if not get_output_vat_account(company):
		return None

	field = "base_tax_amount" if base else "tax_amount"
	return sum(
		flt(tax.get(field))
		for tax in doc.get("taxes") or []
		if is_output_vat_account(tax.get("account_head"), company)
	)


def get_tax_invoice_data(doc) -> dict:
	"""Everything a tax invoice print format needs, in document currency and in AED, so that the
	templates carry no arithmetic. VAT per line is derived from the line's net amount and the VAT
	rate applied to it."""
	company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	conversion_rate = flt(doc.get("conversion_rate")) or 1
	rates = get_item_wise_vat_rates(doc.get("taxes") or [], doc.company)

	lines = []
	for item in doc.items:
		rate = rates.get(item.item_code)
		net = flt(item.net_amount)
		vat = flt(net * flt(rate) / 100, 2) if rate else 0.0
		lines.append(
			{
				"item": item,
				"vat_rate": rate,
				"vat_amount": vat,
				"base_vat_amount": flt(vat * conversion_rate, 2),
				"total": net + vat,
				"base_total": flt(flt(item.get("base_net_amount")) + vat * conversion_rate, 2),
			}
		)

	return {
		"company_currency": company_currency,
		"is_foreign_currency": doc.currency != company_currency,
		"lines": lines,
		"vat": get_output_vat_amount(doc),
		"base_vat": get_output_vat_amount(doc, base=True),
	}


def get_value_before_credit_note(doc, before_creation=None) -> float:
	"""The invoice value (excluding VAT, in company currency) a credit note starts from: the original
	invoice value less the credit notes already submitted against it. `before_creation` restricts
	that to credit notes created earlier, for old credit notes that have no stored value."""
	original = doc.get("return_against")
	if not original:
		return 0.0

	filters = {
		"return_against": original,
		"docstatus": 1,
		"name": ["!=", doc.get("name")],
	}
	if before_creation:
		filters["creation"] = ["<", before_creation]

	earlier = frappe.db.get_all("Sales Invoice", filters=filters, fields=["sum(base_net_total) as total"])
	earlier_total = flt(earlier[0].total) if earlier else 0.0

	return flt(frappe.db.get_value("Sales Invoice", original, "base_net_total")) + earlier_total


def get_credit_note_values(doc) -> dict:
	"""Figures a tax credit note must show (ER Art 60(1)), in company currency (AED): the original
	value, the corrected value, the difference and the tax on the difference. Several credit notes
	against one invoice each start from the value left after the earlier ones.

	The starting value is stored on the credit note when it is submitted, so reprinting it never
	changes with the order other credit notes were drafted in. A draft shows a live preview, and a
	credit note submitted before the value was stored falls back to creation order."""
	if not doc.get("return_against"):
		return {}

	stored = flt(doc.get("uae_credit_note_original_value"))
	if doc.get("docstatus") == 1:
		before = stored or get_value_before_credit_note(doc, doc.get("creation"))
	else:
		before = get_value_before_credit_note(doc)

	difference = flt(doc.get("base_net_total"))

	return {
		"original_value": before,
		"difference": difference,
		"corrected_value": before + difference,
		"tax_on_difference": get_output_vat_amount(doc, base=True),
	}
