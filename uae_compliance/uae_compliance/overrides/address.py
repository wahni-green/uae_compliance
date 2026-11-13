import frappe
from frappe import _

from uae_compliance.uae_compliance.utils.company import UAE


def validate(doc, method=None):
	"""The emirate goes into the e-invoice (IBT-054) and the VAT 201 return, so an address in the UAE
	cannot be saved without it. The form enforces this too; this covers imports and the API."""
	if doc.country == UAE and not doc.get("uae_emirate"):
		frappe.throw(_("Set the Emirate: the address is in the UAE."), title=_("Emirate Missing"))
