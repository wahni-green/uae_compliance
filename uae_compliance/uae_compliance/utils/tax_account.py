import json

import frappe


def get_output_vat_account(company: str | None) -> str | None:
	"""The company's configured Output VAT account (UAE Compliance Settings, one row per company)."""
	return _get_vat_row_value(company, "output_vat_account")


def get_input_vat_account(company: str | None) -> str | None:
	"""The company's configured Input VAT account (also the offset for self-accounted reverse charge)."""
	return _get_vat_row_value(company, "input_vat_account")


def get_excise_tax_account(company: str | None) -> str | None:
	"""The company's configured Excise Tax account (UAE Compliance Settings)."""
	return _get_vat_row_value(company, "excise_tax_account")


def _get_vat_row_value(company: str | None, fieldname: str) -> str | None:
	# Explicitly configured, not guessed from account type: ERPNext's generic account types are
	# shared with unrelated charges (freight, discount, ...).
	if not company:
		return None

	settings = frappe.get_cached_doc("UAE Compliance Settings")
	for row in settings.vat_accounts:
		if row.company == company:
			return row.get(fieldname)

	return None


def is_output_vat_account(account_head: str | None, company: str | None) -> bool:
	return bool(account_head) and account_head == get_output_vat_account(company)


def is_input_vat_account(account_head: str | None, company: str | None) -> bool:
	return bool(account_head) and account_head == get_input_vat_account(company)


def get_item_wise_vat_rates(tax_rows, company: str | None, is_matching_account=None) -> dict[str, float]:
	"""Sum of item_wise_tax_detail VAT rates for rows posted to the VAT account that
	`is_matching_account` identifies (default: the company's Output VAT account, right for sales;
	pass `is_input_vat_account` for purchases), keyed by item_code. Unrelated charges (freight,
	discount, ...) with their own item-wise rate are never read as VAT. Returns nothing if that
	account is not configured."""
	is_matching_account = is_matching_account or is_output_vat_account
	rates: dict[str, float] = {}

	for tax in tax_rows:
		if not is_matching_account(tax.get("account_head"), company):
			continue

		detail = tax.get("item_wise_tax_detail")
		if not detail:
			continue

		parsed = json.loads(detail) if isinstance(detail, str) else detail
		for item_code, detail_row in parsed.items():
			rates[item_code] = rates.get(item_code, 0) + detail_row[0]

	return rates


def get_item_wise_vat_amounts(tax_rows, company: str | None, is_matching_account) -> dict[str, float]:
	"""Sum of item_wise_tax_detail VAT amounts (company currency) for rows posted to whichever
	account `is_matching_account` identifies, keyed by item_code. Shared by the VAT return."""
	amounts: dict[str, float] = {}

	for tax in tax_rows:
		if not is_matching_account(tax.get("account_head"), company):
			continue

		detail = tax.get("item_wise_tax_detail")
		if not detail:
			continue

		parsed = json.loads(detail) if isinstance(detail, str) else detail
		for item_code, detail_row in parsed.items():
			amounts[item_code] = amounts.get(item_code, 0) + detail_row[1]

	return amounts


def is_einvoicing_company(company: str | None) -> bool:
	"""Whether the company is flagged in UAE Compliance Settings as issuing e-invoices."""
	if not company:
		return False

	settings = frappe.get_cached_doc("UAE Compliance Settings")
	return any(row.company == company and row.issues_e_invoices for row in settings.vat_accounts)
