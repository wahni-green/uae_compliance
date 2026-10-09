import frappe
from frappe import _

from uae_compliance.uae_compliance.constants import DEFAULT_VAT_CATEGORY
from uae_compliance.uae_compliance.utils.company import is_uae_company
from uae_compliance.uae_compliance.utils.vat_category import (
	get_designated_zone,
	get_item_category,
	get_item_tax_template_category,
)


def set_vat_category_defaults(doc, method=None):
	"""Shared by Sales Order, Quotation, Delivery Note and Sales Invoice. Fills a blank row category
	only, never overwriting one already set. Precedence: the row's Item Tax Template, then the Item
	master's default, then Standard Rated.

	A designated zone address never zero-rates a row automatically: goods supplied within a zone are
	inside the UAE by default and are outside only with evidence (ER Art 51(5)), so this only warns."""
	if not is_uae_company(doc.get("company")):
		return

	for row in doc.get("items", []):
		if row.get("uae_vat_category"):
			continue

		row.uae_vat_category = (
			get_item_tax_template_category(row.get("item_tax_template"))
			or get_item_category(row.get("item_code"))
			or DEFAULT_VAT_CATEGORY
		)

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
