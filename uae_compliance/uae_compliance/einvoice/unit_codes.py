"""The UN/ECE unit code of a line (IBT-130). Finance keeps it on the UOM, so a unit is never guessed:
an invoice with a unit that has no code is stopped, not sent as a piece."""

import frappe
from frappe import _

from uae_compliance.uae_compliance.einvoice.exceptions import EInvoiceError


def get_unit_code(uom: str | None) -> str | None:
	return uom and frappe.get_cached_value("UOM", uom, "uae_uncefact_code") or None


def validate_unit_codes(doc) -> None:
	"""Stop an invoice with a unit of measure that has no UN/ECE code."""
	missing = sorted({row.uom for row in doc.items if not get_unit_code(row.uom)})
	if missing:
		frappe.throw(
			_("Set the UN/ECE Code on the unit of measure: {0}.").format(
				", ".join(map(frappe.bold, missing))
			),
			exc=EInvoiceError,
			title=_("Unit Code Missing"),
		)
