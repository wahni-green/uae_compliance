import frappe
from frappe import _

from uae_compliance.uae_compliance.utils.vat_category import get_item_category


def validate(doc, method=None):
	"""A bundle of interconnected components that cannot be separated is one composite supply, taxed
	by its principal component (Executive Regulation Art 4(6), added by Cabinet Decision 149/2026). A
	Product Bundle is one invoice row for its parent item, so the bundle item carries the one VAT
	category. This lets the principal component be named and warns when the bundle item's VAT category
	differs from it."""
	principal = doc.get("uae_principal_item")
	if not principal:
		return

	if principal not in {row.item_code for row in doc.get("items") or []}:
		frappe.throw(
			_("The Principal Component {0} must be one of the items in the bundle.").format(
				frappe.bold(principal)
			),
			title=_("Principal Component"),
		)

	bundle_category = get_item_category(doc.new_item_code)
	principal_category = get_item_category(principal)
	if principal_category and bundle_category != principal_category:
		frappe.msgprint(
			_(
				"The bundle item {0} has the VAT Category {1}, but the bundle is taxed by its principal component {2}, which is {3}. Set the bundle item's VAT Category and tax template to match."
			).format(
				frappe.bold(doc.new_item_code),
				frappe.bold(_(bundle_category) if bundle_category else _("not set")),
				frappe.bold(principal),
				frappe.bold(_(principal_category)),
			),
			indicator="orange",
			title=_("Composite Supply"),
		)
