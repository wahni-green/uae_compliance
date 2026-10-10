"""Input VAT on a large payment in cash (Executive Regulation Art 54(3), added by Cabinet Decision
149/2026): it is not recoverable where the supply's value exceeds an amount set by decision of the
Minister of Finance and the consideration is paid in cash. The amount had not been published when this
was written, so it is a setting, and the rule is off while it is empty."""

import frappe
from frappe.utils import flt


def get_cash_payment_limit() -> float:
	return flt(frappe.db.get_single_value("UAE Compliance Settings", "cash_payment_limit"))


def get_cash_modes_of_payment() -> set[str]:
	return set(frappe.get_all("Mode of Payment", filters={"type": "Cash"}, pluck="name"))


def exceeds_cash_limit(invoice, limit: float | None = None) -> bool:
	"""Whether a Purchase Invoice's value is above the limit. The value of the supply counts, not
	the cash part: the regulation refers to the supply's value."""
	limit = get_cash_payment_limit() if limit is None else limit
	return bool(limit) and not invoice.get("is_return") and abs(flt(invoice.get("base_grand_total"))) > limit


def get_invoices_paid_in_cash_over_limit(invoices: dict) -> set[str]:
	"""The names of the Purchase Invoices that are paid in cash, on the invoice itself or by a submitted
	Payment Entry, or are marked as intended to be paid in cash, and whose value is above the limit.
	Empty while no limit is set."""
	limit = get_cash_payment_limit()
	if not limit or not invoices:
		return set()

	candidates = {name for name, invoice in invoices.items() if exceeds_cash_limit(invoice, limit)}
	if not candidates:
		return set()

	# The regulation also covers a payment intended to be made in cash, before it happens.
	paid = {name for name in candidates if invoices[name].get("uae_cash_payment_intended")}

	cash_modes = get_cash_modes_of_payment()
	if not cash_modes:
		return paid

	paid |= {
		name
		for name in candidates
		if invoices[name].get("is_paid") and invoices[name].get("mode_of_payment") in cash_modes
	}

	remaining = list(candidates - paid)
	if remaining:
		references = frappe.get_all(
			"Payment Entry Reference",
			filters={"reference_doctype": "Purchase Invoice", "reference_name": ["in", remaining]},
			fields=["parent", "reference_name"],
		)
		entries = {
			entry.name
			for entry in frappe.get_all(
				"Payment Entry",
				filters={
					"name": ["in", list({ref.parent for ref in references}) or [""]],
					"docstatus": 1,
					"payment_type": "Pay",
					"mode_of_payment": ["in", list(cash_modes)],
				},
				fields=["name"],
			)
		}
		paid |= {ref.reference_name for ref in references if ref.parent in entries}

	return paid
