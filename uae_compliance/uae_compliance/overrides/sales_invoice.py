import frappe
from frappe import _
from frappe.utils import date_diff, flt

from uae_compliance.uae_compliance.constants import TAX_INVOICE_ISSUE_DAYS
from uae_compliance.uae_compliance.overrides.sales_schemes import (
	validate_margin_scheme,
	validate_tourist_refund,
	warn_if_excise_missing,
)
from uae_compliance.uae_compliance.overrides.transaction import set_vat_category_defaults
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


def validate(doc, method=None):
	if not is_uae_company(doc.get("company")):
		return

	set_vat_category_defaults(doc)
	validate_vat_category_tax_consistency(doc)
	validate_no_mixed_vat_category_per_item_code(doc)
	set_export_flag(doc)
	set_simplified_tax_invoice_flag(doc)
	warn_late_tax_invoice(doc)
	validate_margin_scheme(doc)
	validate_reverse_charge_supply(doc)
	validate_tourist_refund(doc)
	warn_if_excise_missing(doc)


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
