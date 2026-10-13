import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate

from uae_compliance.uae_compliance.constants import TAX_INVOICE_ISSUE_DAYS
from uae_compliance.uae_compliance.constants.einvoice import STATUS_INVALID
from uae_compliance.uae_compliance.overrides.sales_schemes import (
	validate_margin_scheme,
	validate_tourist_refund,
	warn_if_excise_missing,
)
from uae_compliance.uae_compliance.overrides.transaction import clear_uae_fields, set_vat_category_defaults
from uae_compliance.uae_compliance.overrides.vat_checks import (
	validate_no_mixed_vat_category_per_item_code,
	validate_vat_category_tax_consistency,
)
from uae_compliance.uae_compliance.utils.company import is_uae_company
from uae_compliance.uae_compliance.utils.print_data import get_value_before_credit_note
from uae_compliance.uae_compliance.utils.tax_account import (
	get_item_wise_vat_rates,
	is_einvoicing_company,
	is_output_vat_account,
)
from uae_compliance.uae_compliance.utils.trn import validate_trn


def validate(doc, method=None):
	if not is_uae_company(doc.get("company")):
		clear_uae_fields(doc)
		return

	set_vat_category_defaults(doc)
	validate_vat_category_tax_consistency(doc)
	validate_no_mixed_vat_category_per_item_code(doc)
	set_export_flag(doc)
	set_simplified_tax_invoice_flag(doc)
	set_supply_date(doc)
	warn_late_tax_invoice(doc)
	validate_margin_scheme(doc)
	validate_reverse_charge_supply(doc)
	validate_tourist_refund(doc)
	validate_billing_types(doc)
	set_einvoice_exclusion(doc)
	warn_if_excise_missing(doc)


def get_dashboard_data(data):
	"""Show the invoice's E-Invoice Logs under Connections. The log points back through a Dynamic Link."""
	data["non_standard_fieldnames"] = {
		**data.get("non_standard_fieldnames", {}),
		"UAE E-Invoice Log": "reference_name",
	}
	data["dynamic_links"] = {
		**data.get("dynamic_links", {}),
		"reference_name": ["Sales Invoice", "reference_doctype"],
	}
	data["transactions"].append({"label": _("E-Invoice"), "items": ["UAE E-Invoice Log"]})
	return data


def set_einvoice_exclusion(doc) -> None:
	"""An invoice whose rows all carry the same E-Invoice Exclusion on their Items is left out of
	e-invoicing. A reason copied from the Items follows the rows when they change; a reason chosen on
	the invoice is kept."""
	reason = doc.get("uae_einvoice_exclusion")
	if reason and doc.get("uae_einvoice_exclusion_from_items"):
		# Another reason than the saved one, copied from the Items, was chosen by the user.
		before = doc.get_doc_before_save()
		if before and before.get("uae_einvoice_exclusion") != reason:
			doc.uae_einvoice_exclusion_from_items = 0

	if reason and not doc.get("uae_einvoice_exclusion_from_items"):
		return

	reasons = {frappe.get_cached_value("Item", row.item_code, "uae_einvoice_exclusion") for row in doc.items}
	reason = reasons.pop() if len(reasons) == 1 else None
	doc.uae_einvoice_exclusion = reason or ""
	doc.uae_einvoice_exclusion_from_items = 1 if reason else 0


# Only an invoice that is not logged, or whose retry rebuilds the document (Invalid), can still take the
# frequency: one waiting to be sent, sent, rejected (its number is not reused) or failed (which the
# provider may hold) cannot.
EDITABLE_STATUSES = (None, "", STATUS_INVALID)


def before_update_after_submit(doc, method=None):
	if is_uae_company(doc.get("company")):
		validate_billing_frequency_after_submit(doc)


def validate_billing_frequency_after_submit(doc) -> None:
	"""The frequency can be filled in on a submitted summary invoice that lacks it, so that it can be
	sent, but never changed once it has a value or the invoice has been sent."""
	if doc.docstatus != 1:
		return

	before = doc.get_doc_before_save()
	if not before or before.get("uae_billing_frequency") == doc.get("uae_billing_frequency"):
		return

	if before.get("uae_billing_frequency") or doc.get("uae_einvoice_status") not in EDITABLE_STATUSES:
		frappe.throw(
			_(
				"The Frequency of Billing can only be filled in while it is blank and the e-invoice has not been sent or is waiting to be sent."
			),
			title=_("Frequency of Billing"),
		)


def validate_billing_types(doc) -> None:
	"""The summary invoice, continuous supply and disclosed agent billing transaction types of the
	e-invoice. A summary invoice needs the period it covers (rule ibr-138-ae), a disclosed agent bills
	for a principal with another TRN than its own (rules ibr-137-ae and ibr-176-ae)."""
	start, end = doc.get("uae_invoice_period_start"), doc.get("uae_invoice_period_end")
	if doc.get("uae_is_summary_invoice"):
		if not (start and end and doc.get("uae_billing_frequency")):
			frappe.throw(
				_("A summary invoice needs the Invoice Period Start and End and the Frequency of Billing."),
				title=_("Summary Invoice"),
			)

		if all(row.get("uae_vat_category") in ("Exempt", "Out of Scope") for row in doc.items):
			frappe.throw(
				_("A summary invoice cannot have only exempt or out of scope rows (rule ibr-157-ae)."),
				title=_("Summary Invoice"),
			)

	has_period = start or end or doc.get("uae_billing_frequency")
	if has_period and not (doc.get("uae_is_summary_invoice") or doc.get("uae_is_continuous_supply")):
		frappe.throw(
			_("The invoice period belongs to a summary invoice or a continuous supply: tick one of them."),
			title=_("Invoice Period"),
		)

	if bool(start) != bool(end):
		frappe.throw(_("Enter both the start and the end of the invoice period."), title=_("Invoice Period"))

	if start and end and getdate(start) > getdate(end):
		frappe.throw(_("The invoice period cannot end before it starts."), title=_("Invoice Period"))

	if doc.get("uae_is_agent_billing"):
		principal = validate_trn(doc.get("uae_principal_trn"), label="Principal TRN")
		if not principal:
			frappe.throw(_("Enter the Principal TRN."), title=_("Disclosed Agent Billing"))

		doc.uae_principal_trn = principal
		if principal == frappe.db.get_value("Company", doc.company, "uae_trn"):
			frappe.throw(
				_("The principal cannot be the company itself: it bills as the agent of another person."),
				title=_("Disclosed Agent Billing"),
			)
	elif doc.get("uae_principal_trn"):
		frappe.throw(
			_("The Principal TRN belongs to disclosed agent billing: tick it."), title=_("Principal")
		)


def validate_reverse_charge_supply(doc) -> None:
	"""A supply the recipient accounts for the VAT on (CD 127/2024 and CD 153/2025 Art 2): the supplier
	charges and reports no VAT, must hold the recipient's declarations, and may not use it for a zero
	rated supply, which the decisions exclude. Every row is then a standard rated supply."""
	if not doc.get("uae_is_reverse_charge"):
		return

	if not doc.get("uae_reverse_charge_type"):
		frappe.throw(_("Choose the Reverse Charge Type."), title=_("Reverse Charge"))

	if not doc.get("uae_rc_declaration"):
		frappe.throw(
			_(
				"Tick Recipient Declarations Held: before the supply the supplier must hold the recipient's written declarations of intended use and of registration."
			),
			title=_("Reverse Charge"),
		)

	if not frappe.db.get_value("Customer", doc.customer, "uae_trn"):
		frappe.throw(
			_("The customer needs a TRN: a reverse charge supply is only made to a registered recipient."),
			title=_("Reverse Charge"),
		)

	if doc.get("uae_is_export") or doc.get("uae_is_margin_scheme") or doc.get("uae_tourist_refund"):
		frappe.throw(
			_(
				"A reverse charge supply cannot be an export, a margin scheme supply or have a tourist refund."
			),
			title=_("Reverse Charge"),
		)

	if any(row.get("uae_vat_category") != "Standard Rated" for row in doc.get("items") or []):
		frappe.throw(
			_(
				"Every row of a reverse charge supply must be Standard Rated: it does not apply to zero rated, exempt or out of scope supplies."
			),
			title=_("Reverse Charge"),
		)

	# Both the rates and the amounts: an Actual charge on the Output VAT account has a tax amount but no
	# item-wise rate.
	charged = get_item_wise_vat_rates(doc.get("taxes") or [], doc.get("company"), is_output_vat_account)
	charged_amount = sum(
		abs(flt(tax.get("tax_amount")))
		for tax in doc.get("taxes") or []
		if is_output_vat_account(tax.get("account_head"), doc.get("company"))
	)
	if any(charged.values()) or charged_amount:
		frappe.throw(
			_("A reverse charge supply carries no VAT: remove the Output VAT from the taxes."),
			title=_("Reverse Charge"),
		)


def before_submit(doc, method=None):
	if not is_uae_company(doc.get("company")):
		return

	validate_emirate(doc)
	validate_credit_note_reason(doc)
	store_value_before_credit_note(doc)


def store_value_before_credit_note(doc) -> None:
	"""Fix the value a credit note starts from at the moment it is submitted, so that it follows the
	order of issue and not the order the drafts were created in."""
	if doc.get("is_return") and doc.get("return_against"):
		doc.uae_credit_note_original_value = get_value_before_credit_note(doc)


def validate_credit_note_reason(doc) -> None:
	"""A tax credit note must state a brief reason (ER Art 60(1))."""
	if doc.get("is_return") and not (doc.get("uae_credit_note_reason") or "").strip():
		frappe.throw(
			_("Reason for Credit Note is required: a tax credit note must state why it was issued."),
			title=_("Reason Missing"),
		)


def validate_emirate(doc) -> None:
	"""Standard rated supplies are reported per emirate in VAT 201 box 1 (1a-1g)."""
	has_standard_rated = any(row.get("uae_vat_category") == "Standard Rated" for row in doc.items)
	if has_standard_rated and not doc.get("uae_emirate"):
		frappe.throw(
			_(
				"VAT Emirate is required: standard rated supplies are reported per emirate. Set the"
				" Emirate on the company address or select it on this invoice."
			),
			title=_("VAT Emirate Missing"),
		)


def set_export_flag(doc) -> None:
	"""Shipping address is the better signal of where goods go than the customer (billing)
	address, so it is checked first."""
	previous_value = bool(doc.get("uae_is_export"))
	doc.uae_is_export = is_export_candidate(doc)

	if previous_value != doc.uae_is_export:
		frappe.msgprint(
			_("Export set to {0}, based on the Shipping/Customer Address's country.").format(
				_("Yes") if doc.uae_is_export else _("No")
			),
			indicator="blue",
			alert=True,
		)


def is_export_candidate(doc) -> bool:
	address = doc.get("shipping_address_name") or doc.get("customer_address")
	if not address:
		return False

	address_country = frappe.db.get_value("Address", address, "country")
	company_country = frappe.get_cached_value("Company", doc.company, "country")
	if not address_country or not company_country:
		return False

	return address_country != company_country


def set_simplified_tax_invoice_flag(doc) -> None:
	"""Drives the print format's choice between the full and simplified layout. Simplified tax
	invoices are optional, so this is conservative: only unregistered recipients, up to the
	threshold, and never for e-invoicing companies (ER Art 59(5), 59(16))."""
	previous_value = bool(doc.get("uae_is_simplified_tax_invoice"))
	doc.uae_is_simplified_tax_invoice = is_simplified_tax_invoice_candidate(doc)

	if previous_value != doc.uae_is_simplified_tax_invoice:
		frappe.msgprint(
			_("Simplified Tax Invoice set to {0}, based on the total and the Customer TRN.").format(
				_("Yes") if doc.uae_is_simplified_tax_invoice else _("No")
			),
			indicator="blue",
			alert=True,
		)


def is_simplified_tax_invoice_candidate(doc) -> bool:
	company = doc.get("company")
	if is_einvoicing_company(company):
		return False

	# A simplified tax invoice is not allowed for a supply under the reverse charge (ER Art 59(2)).
	if doc.get("uae_is_reverse_charge"):
		return False

	settings = frappe.get_cached_doc("UAE Compliance Settings")
	threshold = flt(settings.simplified_tax_invoice_threshold)
	if not threshold:
		return False

	# The threshold is in AED, so it is only comparable when the company's base currency is AED.
	if frappe.get_cached_value("Company", company, "default_currency") != settings.settings_currency:
		return False

	# "Consideration" in the Executive Regulation includes the tax. Absolute value: a return has a
	# negative total and must not slip through regardless of size.
	if abs(flt(doc.get("base_grand_total"))) > threshold:
		return False

	customer = doc.get("customer")
	if not customer:
		return False

	return not frappe.db.get_value("Customer", customer, "uae_trn")


def set_supply_date(doc) -> None:
	"""A date the user entered stays. One this method filled in follows its source: it is replaced
	when the posting date, Update Stock or the Delivery Notes change, so it is told apart by
	matching what the saved invoice would have defaulted to."""
	if doc.get("is_return"):
		doc.uae_supply_date = None
		return

	current = doc.get("uae_supply_date")
	saved = doc.get_doc_before_save() if callable(getattr(doc, "get_doc_before_save", None)) else None
	if current and not (
		saved
		and getdate(current)
		== _as_date(saved.get("uae_supply_date"))
		== _as_date(get_default_supply_date(saved))
	):
		return

	doc.uae_supply_date = get_default_supply_date(doc)


def _as_date(value):
	return getdate(value) if value else None


def get_default_supply_date(doc):
	"""The goods left with this invoice when it updates stock, so the supply is on its posting date.
	When it bills Delivery Notes the supply is the earliest of their dates."""
	if doc.get("update_stock"):
		return doc.get("posting_date")

	delivery_notes = {row.delivery_note for row in doc.get("items") or [] if row.get("delivery_note")}
	if delivery_notes:
		dates = frappe.get_all(
			"Delivery Note", filters={"name": ("in", list(delivery_notes))}, pluck="posting_date"
		)
		return min(dates) if dates else None

	return None


def warn_late_tax_invoice(doc) -> None:
	"""A tax invoice must be issued within 14 days of the supply (Decree-Law Art 67)."""
	supply_date = doc.get("uae_supply_date")
	if not supply_date or doc.get("is_return") or not doc.get("posting_date"):
		return

	if date_diff(doc.posting_date, supply_date) > TAX_INVOICE_ISSUE_DAYS:
		frappe.msgprint(
			_("This tax invoice is dated more than {0} days after the supply date.").format(
				TAX_INVOICE_ISSUE_DAYS
			),
			indicator="orange",
			alert=True,
		)
