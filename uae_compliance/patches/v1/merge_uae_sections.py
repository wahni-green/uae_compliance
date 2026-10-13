import frappe

OBSOLETE = (
	"Customer-uae_legal_section",
	"Customer-uae_cb_legal_1",
	"Item-uae_cb_item_2",
	"Item-uae_cb_item_5",
	"Item-uae_excise_section",
	"Item-uae_einvoice_section",
)


def execute():
	"""The UAE fields of an Item, Customer and Supplier sit in one "UAE Compliance" section of the
	Tax tab instead of several."""
	for name in OBSOLETE:
		frappe.delete_doc("Custom Field", name, ignore_missing=True, force=True)
