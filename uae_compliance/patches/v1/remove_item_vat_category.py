import frappe


def execute():
	"""An Item takes its VAT Category from its default Item Tax Template, so it no longer has a
	field of its own."""
	frappe.delete_doc("Custom Field", "Item-uae_vat_category", ignore_missing=True, force=True)
	frappe.delete_doc("Custom Field", "Item-uae_cb_item_1", ignore_missing=True, force=True)
