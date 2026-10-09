import frappe


def get_item_tax_template_category(item_tax_template: str | None) -> str | None:
	"""VAT Category declared on an Item Tax Template, if any. The most reliable signal: a template's
	rate alone can't tell Zero Rated from Exempt from Out of Scope, which are all 0% but are
	reported in different VAT 201 boxes."""
	if not item_tax_template:
		return None

	# Normalize "" (unset Select) to None so the contract means "no category declared".
	return frappe.get_cached_value("Item Tax Template", item_tax_template, "uae_vat_category") or None


def get_item_category(item_code: str | None) -> str | None:
	"""The default VAT Category set on the Item master, if any."""
	if not item_code:
		return None

	return frappe.get_cached_value("Item", item_code, "uae_vat_category") or None


def get_designated_zone(address_name: str | None) -> str | None:
	"""The active UAE Designated Zone linked to an Address, if any."""
	if not address_name:
		return None

	zone = frappe.db.get_value("Address", address_name, "uae_designated_zone")
	if zone and frappe.db.get_value("UAE Designated Zone", zone, "is_active"):
		return zone

	return None
