import frappe
from frappe import _

COMMERCIAL_ROUNDING = "Commercial Rounding"


def warn_if_not_commercial_rounding() -> None:
	"""PINT AE rounds half up, like Commercial Rounding. Banker's Rounding can make the VAT of an
	invoice differ from the network's by 0.01. The setting is site wide, so it is only warned about."""
	method = frappe.db.get_single_value("System Settings", "rounding_method")
	if method and method != COMMERCIAL_ROUNDING:
		frappe.msgprint(
			_(
				"System Settings use {0}. Set the Rounding Method to {1} so that VAT agrees with the e-invoice."
			).format(frappe.bold(_(method)), frappe.bold(_(COMMERCIAL_ROUNDING))),
			title=_("Rounding Method"),
			indicator="orange",
			alert=True,
		)
