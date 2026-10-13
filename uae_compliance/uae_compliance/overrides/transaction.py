import frappe
from frappe import _

from uae_compliance.uae_compliance.constants import DEFAULT_VAT_CATEGORY
from uae_compliance.uae_compliance.constants.custom_fields import get_value_fieldnames
from uae_compliance.uae_compliance.utils.company import is_uae_company
from uae_compliance.uae_compliance.utils.tax_account import get_output_vat_account
from uae_compliance.uae_compliance.utils.vat_category import (
	get_designated_zone,
	get_item_tax_template_category,
)


def clear_uae_fields(doc) -> None:
	"""The UAE tab is hidden for a company outside the UAE, so nothing entered before the company
	changed should linger on it."""
	for fieldname in get_value_fieldnames(doc.doctype):
		doc.set(fieldname, None)


def validate_uae_fields(doc, method=None):
	"""Sales Order and Delivery Note: their only UAE header field is the VAT Emirate."""
	if not is_uae_company(doc.get("company")):
		clear_uae_fields(doc)


def is_vat_applied(doc) -> bool:
	"""Whether the document charges any VAT. Unknown (so true) when the company's Output VAT account
	is not configured, as no row can then be told apart from a freight or discount charge. A reverse
	charge supply carries no VAT row, and a margin scheme supply can owe none, but both are still
	standard rated."""
	if doc.get("uae_is_reverse_charge") or doc.get("uae_is_margin_scheme"):
		return True

	output_account = get_output_vat_account(doc.get("company"))
	if not output_account:
		return True

	return any(
		row.get("account_head") == output_account and (row.get("rate") or row.get("tax_amount"))
		for row in doc.get("taxes") or []
	)


def set_vat_category_defaults(doc, method=None):
	"""Shared by Sales Order, Quotation, Delivery Note and Sales Invoice. A row's category is the one
	declared by its Item Tax Template, re-read on every save so that changing the template changes
	the category. A row without one keeps the category already set, else gets Zero Rated when the
	document charges no VAT, else Standard Rated.

	A designated zone address never zero-rates a row automatically: goods supplied within a zone are
	inside the UAE by default and are outside only with evidence (ER Art 51(5)), so this only warns."""
	if not is_uae_company(doc.get("company")):
		return

	default = DEFAULT_VAT_CATEGORY if is_vat_applied(doc) else "Zero Rated"
	for row in doc.get("items", []):
		template_category = get_item_tax_template_category(row.get("item_tax_template"))
		if template_category:
			row.uae_vat_category = template_category
		elif not row.get("uae_vat_category"):
			row.uae_vat_category = default

	warn_designated_zone(doc)


def warn_designated_zone(doc) -> None:
	zone = None
	for address in (
		doc.get("customer_address"),
		doc.get("shipping_address_name"),
		doc.get("dispatch_address_name"),
		doc.get("supplier_address"),
		doc.get("dispatch_address"),
	):
		zone = get_designated_zone(address)
		if zone:
			break

	if not zone:
		return

	frappe.msgprint(
		_(
			"An address on this document is in the designated zone {0}. Goods supplied within a"
			" designated zone are inside the UAE for VAT unless the conditions of Executive Regulation"
			" Art 51 are met. Review the VAT Category of each row."
		).format(frappe.bold(zone)),
		indicator="orange",
		alert=True,
	)
