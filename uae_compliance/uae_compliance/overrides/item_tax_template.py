import frappe
from frappe import _

from uae_compliance.uae_compliance.constants import NO_TAX_VAT_CATEGORIES
from uae_compliance.uae_compliance.utils.tax_account import (
	get_input_vat_account,
	get_output_vat_account,
	is_input_vat_account,
	is_output_vat_account,
)


def validate(doc, method=None):
	validate_vat_category_tax_consistency(doc)


def validate_vat_category_tax_consistency(doc):
	"""A Zero Rated / Exempt / Out of Scope template must not post a nonzero rate to the company's
	configured VAT accounts."""
	if doc.get("uae_vat_category") not in NO_TAX_VAT_CATEGORIES or not doc.company:
		return

	for row in doc.get("taxes") or []:
		if not row.tax_rate:
			continue

		if is_output_vat_account(row.tax_type, doc.company) or is_input_vat_account(
			row.tax_type, doc.company
		):
			frappe.throw(
				_(
					"Row #{0}: this template is marked {1} but posts a {2}% rate to {3}, one of this"
					" Company's configured VAT Accounts."
				).format(row.idx, doc.uae_vat_category, row.tax_rate, frappe.bold(row.tax_type)),
				title=_("VAT Category Mismatch"),
			)


@frappe.whitelist()
def get_vat_accounts_for_template(company: str) -> list[str]:
	"""The company's configured Output/Input VAT accounts, de-duplicated, for the "Fetch VAT
	Accounts" button on Item Tax Template."""
	frappe.has_permission("Item Tax Template", "read", throw=True)
	frappe.has_permission("Company", "read", doc=company, throw=True)

	return list(
		dict.fromkeys(
			account
			for account in (get_output_vat_account(company), get_input_vat_account(company))
			if account
		)
	)
