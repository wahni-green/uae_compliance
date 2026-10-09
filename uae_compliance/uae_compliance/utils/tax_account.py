import frappe


def get_output_vat_account(company: str | None) -> str | None:
	"""The company's configured Output VAT account (UAE Compliance Settings, one row per company)."""
	return _get_vat_row_value(company, "output_vat_account")


def get_input_vat_account(company: str | None) -> str | None:
	"""The company's configured Input VAT account (also the offset for self-accounted reverse charge)."""
	return _get_vat_row_value(company, "input_vat_account")


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
