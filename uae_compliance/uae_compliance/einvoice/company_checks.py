"""The seller details an e-invoice needs from the Company.

The network rejects an invoice without them (ibr-173-ae, ibr-172-ae), after it was already submitted.
So they are checked when the Company is saved and again when an invoice is submitted, which also
catches a Company saved before e-invoicing was enabled."""

import frappe
from frappe import _

TRADE_LICENSE = "Trade License"


def get_registration_problems(values) -> list[str]:
	"""What is missing from the registration of a company, as messages. `values` is anything with
	`.get()`, such as a Company document."""
	if not values.get("uae_legal_registration_type"):
		return [_("Set the Legal Registration Type of the company on its UAE Compliance tab.")]

	if values.get("uae_legal_registration_type") == TRADE_LICENSE and not values.get("uae_licence_authority"):
		return [_("Set the Licence Issuing Authority of the company on its UAE Compliance tab.")]

	return []


def validate_company_registration(company: str) -> None:
	"""Stop an invoice of a company whose registration is incomplete."""
	values = frappe.db.get_value(
		"Company",
		company,
		["uae_legal_registration_type", "uae_licence_authority"],
		as_dict=True,
	)
	problems = get_registration_problems(values)
	if problems:
		frappe.throw("<br>".join(problems), title=_("Company Registration Incomplete"))
