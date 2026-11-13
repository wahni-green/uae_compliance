"""Charges in the taxes table that are not VAT.

PINT AE can carry a document level charge, but each one needs a VAT category, which ERPNext does not
record on a taxes row. So a charge is entered as an item row instead, which has one."""

import frappe
from frappe import _
from frappe.utils import flt

from uae_compliance.uae_compliance.einvoice.exceptions import EInvoiceError
from uae_compliance.uae_compliance.utils.tax_account import is_output_vat_account


def validate_no_extra_charges(doc) -> None:
	"""Stop an invoice whose taxes table holds a charge other than VAT, such as freight."""
	charges = [
		row.get("description") or row.get("account_head")
		for row in doc.get("taxes") or []
		if flt(row.get("tax_amount")) and not is_output_vat_account(row.get("account_head"), doc.company)
	]
	if charges:
		frappe.throw(
			_(
				"The taxes table has a charge that is not VAT: {0}. Enter it as an item row (for example a"
				" freight service item) so that it carries a VAT category, and remove it from the taxes table."
			).format(", ".join([frappe.bold(charge) for charge in charges])),
			exc=EInvoiceError,
			title=_("Charge in the Taxes Table"),
		)
