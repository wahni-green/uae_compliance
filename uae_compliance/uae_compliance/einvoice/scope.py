"""Whether a Sales Invoice has to be sent as an e-invoice, and if not, why not.

The answer is worked out when the invoice is submitted and kept on it, so that it shows on the
invoice what was decided."""

import frappe
from frappe import _
from frappe.utils import getdate

from uae_compliance.uae_compliance.einvoice.registry import get_company_setting
from uae_compliance.uae_compliance.utils.company import is_uae_company

B2C = "B2C"


def get_exclusion_reason(doc, row) -> str | None:
	"""Why this invoice is left out of e-invoicing, or None when it is sent. `row` is the company's
	enabled setting."""
	if row.mandatory_from and getdate(doc.posting_date) < getdate(row.mandatory_from):
		return _("The invoice is dated before the company's e-invoicing start date.")

	if doc.get("uae_einvoice_exclusion"):
		return _("E-Invoice Exclusion: {0}.").format(_(doc.uae_einvoice_exclusion))

	customer = frappe.db.get_value(
		"Customer", doc.customer, ["customer_type", "uae_buyer_category", "represents_company"], as_dict=True
	)
	if customer.customer_type == "Individual" or customer.uae_buyer_category == B2C:
		return _("The sale is to a consumer (B2C).")

	if is_intra_group_sale(doc, customer.represents_company):
		return _("The sale is to a member of the company's VAT group.")

	return None


def is_intra_group_sale(doc, customer_company: str | None) -> bool:
	"""A sale to another member of the company's UAE Tax Group, while the grace period lasts."""
	settings = frappe.get_cached_doc("UAE Compliance Settings")
	if not settings.exclude_intra_vat_group or not customer_company:
		return False

	if settings.intra_group_grace_end and getdate(doc.posting_date) > getdate(settings.intra_group_grace_end):
		return False

	group = frappe.db.get_value("Company", doc.company, "uae_tax_group")
	return bool(group) and frappe.db.get_value("Company", customer_company, "uae_tax_group") == group


def get_setting_if_required(doc):
	"""The company's e-invoicing setting when this invoice has to be sent, else None."""
	if not is_uae_company(doc.get("company")):
		return None

	row = get_company_setting(doc.company)
	if not row or get_exclusion_reason(doc, row):
		return None

	return row


def set_applicability(doc) -> None:
	"""Record on the invoice whether it is sent as an e-invoice, and why not when it is not. Left
	alone for a company that does not send e-invoices."""
	row = is_uae_company(doc.get("company")) and get_company_setting(doc.company)
	if not row:
		return

	reason = get_exclusion_reason(doc, row)
	doc.uae_einvoice_applicable = 0 if reason else 1
	doc.uae_einvoice_exclusion_reason = reason or ""
