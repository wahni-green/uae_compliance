import frappe
from frappe import _
from frappe.utils import flt

from uae_compliance.uae_compliance.constants import (
	DEFAULT_VAT_CATEGORY,
	IMPORT_OF_GOODS_TYPE,
	IMPORT_OF_SERVICES_TYPE,
	METAL_SCRAP_TYPE,
)
from uae_compliance.uae_compliance.constants.gcc_countries import GCC_COUNTRIES
from uae_compliance.uae_compliance.overrides.transaction import warn_designated_zone
from uae_compliance.uae_compliance.overrides.vat_checks import (
	validate_no_mixed_vat_category_per_item_code,
	validate_vat_category_tax_consistency,
)
from uae_compliance.uae_compliance.utils.company import is_uae_company
from uae_compliance.uae_compliance.utils.tax_account import (
	get_input_vat_account,
	get_output_vat_account,
	is_input_vat_account,
	is_output_vat_account,
)
from uae_compliance.uae_compliance.utils.vat_category import (
	get_item_category,
	get_item_tax_template_category,
)
from uae_compliance.uae_compliance.utils.vat_return.cash_payments import exceeds_cash_limit


def validate(doc, method=None):
	if not is_uae_company(doc.get("company")):
		return

	set_vat_category_defaults(doc)
	validate_vat_category_tax_consistency(doc)
	validate_no_mixed_vat_category_per_item_code(doc)
	validate_reverse_charge(doc)
	set_gcc_supplier_flag(doc)
	set_import_of_goods_flag(doc)
	validate_postponed_import_vat(doc)
	warn_designated_zone(doc)
	warn_if_cash_payment_over_limit(doc)


def warn_if_cash_payment_over_limit(doc) -> None:
	"""Input VAT on a supply above the Minister's limit that is paid in cash is not recoverable (ER Art
	54(3)). The VAT return applies it; this tells the user when the payment is on the invoice itself."""
	paid_in_cash = bool(
		doc.get("is_paid")
		and doc.get("mode_of_payment")
		and frappe.db.get_value("Mode of Payment", doc.mode_of_payment, "type") == "Cash"
	)
	if not (paid_in_cash or doc.get("uae_cash_payment_intended")):
		return

	if exceeds_cash_limit(doc):
		frappe.msgprint(
			_(
				"This invoice is above the cash payment limit and is paid, or intended to be paid, in cash, so the input VAT on it is not recoverable (Executive Regulation Art 54(3))."
			),
			indicator="orange",
			alert=True,
		)


def set_vat_category_defaults(doc) -> None:
	for row in doc.get("items", []):
		if row.get("uae_vat_category"):
			continue

		row.uae_vat_category = (
			get_item_tax_template_category(row.get("item_tax_template"))
			or get_item_category(row.get("item_code"))
			or DEFAULT_VAT_CATEGORY
		)


def validate_reverse_charge(doc) -> None:
	if not doc.get("uae_is_reverse_charge"):
		return

	company = doc.get("company")
	missing = [
		label
		for label, account in (
			(_("Output VAT Account"), get_output_vat_account(company)),
			(_("Input VAT Account"), get_input_vat_account(company)),
		)
		if not account
	]
	if missing:
		frappe.throw(
			_(
				"Reverse Charge Applicable requires {0} to be configured for this Company in UAE"
				" Compliance Settings first."
			).format(", ".join(missing)),
			title=_("VAT Accounts Not Configured"),
		)

	# Whether self-accounting is one row or two, on one account or two, is the company's own
	# bookkeeping choice, so a shared Output/Input account may satisfy both checks with one row.
	if not _has_nonzero_row_on(doc, is_output_vat_account):
		frappe.throw(
			_(
				"Reverse Charge Applicable is checked but this Purchase Invoice has no VAT row posted to"
				" the Output VAT Account. Self-accounting requires recording the output VAT liability"
				" as recipient."
			),
			title=_("Reverse Charge Requires Output VAT Row"),
		)

	if not _has_nonzero_row_on(doc, is_input_vat_account):
		frappe.throw(
			_(
				"Reverse Charge Applicable is checked but this Purchase Invoice has no VAT row posted to"
				" the Input VAT Account. Self-accounting also requires the offsetting input VAT credit."
			),
			title=_("Reverse Charge Requires Input VAT Row"),
		)

	validate_reverse_charge_nets_to_zero(doc)

	if doc.get("uae_reverse_charge_type") == METAL_SCRAP_TYPE and not doc.get("uae_rc_declaration"):
		frappe.throw(
			_(
				"Metal scrap reverse charge requires the recipient's declaration to be on file before"
				" the supply date. Tick Recipient Declaration on File once obtained."
			),
			title=_("Declaration Required"),
		)


def validate_reverse_charge_nets_to_zero(doc) -> None:
	"""Self-accounted VAT must not change what the supplier is paid: the output VAT liability and
	the offsetting input VAT credit have to cancel out. Two rows that both add VAT would raise the
	supplier total by the VAT, which the supplier never charged."""
	company = doc.get("company")
	net = 0.0
	for tax in doc.get("taxes") or []:
		account = tax.get("account_head")
		if not (is_output_vat_account(account, company) or is_input_vat_account(account, company)):
			continue

		# Only rows counted in the document total move what the supplier is paid. A "Valuation" row
		# only changes item cost, so it cannot offset the other row.
		if tax.get("category") == "Valuation":
			continue

		amount = flt(tax.get("tax_amount"))
		net += -amount if tax.get("add_deduct_tax") == "Deduct" else amount

	if flt(net, 2):
		frappe.throw(
			_(
				"The reverse charge VAT rows must cancel out so the supplier total is unchanged: add the"
				" VAT to the Input VAT Account and deduct it from the Output VAT Account. They currently"
				" change the total by {0}."
			).format(frappe.bold(flt(net, 2))),
			title=_("Reverse Charge Rows Do Not Net to Zero"),
		)


def _has_nonzero_row_on(doc, is_matching_account) -> bool:
	for tax in doc.get("taxes") or []:
		if not is_matching_account(tax.get("account_head"), doc.get("company")):
			continue

		if flt(tax.get("rate")) or flt(tax.get("tax_amount")):
			return True

	return False


def set_import_of_goods_flag(doc) -> None:
	"""Imports of goods are reported in boxes 6/7, distinct from reverse charge (box 3/10). It is
	derived from where the goods are dispatched from, and recomputed on every save."""
	previous_value = bool(doc.get("uae_is_import_of_goods"))
	doc.uae_is_import_of_goods = is_import_of_goods_candidate(doc) or (
		doc.get("uae_reverse_charge_type") == IMPORT_OF_GOODS_TYPE
	)

	if previous_value != doc.uae_is_import_of_goods:
		frappe.msgprint(
			_("Import of Goods set to {0}, based on the Dispatch Address and Reverse Charge Type.").format(
				_("Yes") if doc.uae_is_import_of_goods else _("No")
			),
			indicator="blue",
			alert=True,
		)


def is_import_of_goods_candidate(doc) -> bool:
	# A purchase explicitly typed as an import of services is never goods, whatever the address.
	if doc.get("uae_reverse_charge_type") == IMPORT_OF_SERVICES_TYPE:
		return False

	dispatch_address = doc.get("dispatch_address")
	if not dispatch_address:
		return False

	dispatch_country = frappe.db.get_value("Address", dispatch_address, "country")
	company_country = frappe.get_cached_value("Company", doc.company, "country")
	if not dispatch_country or not company_country:
		return False

	return dispatch_country != company_country


def set_gcc_supplier_flag(doc) -> None:
	"""Derived from the Supplier Address (who the supplier is), not the Dispatch Address."""
	previous_value = bool(doc.get("uae_is_gcc_supplier"))
	doc.uae_is_gcc_supplier = is_gcc_supplier_candidate(doc)

	if previous_value != doc.uae_is_gcc_supplier:
		frappe.msgprint(
			_("GCC Supplier set to {0}, based on the Supplier Address's country.").format(
				_("Yes") if doc.uae_is_gcc_supplier else _("No")
			),
			indicator="blue",
			alert=True,
		)


def is_gcc_supplier_candidate(doc) -> bool:
	supplier_address = doc.get("supplier_address")
	if not supplier_address:
		return False

	country = frappe.db.get_value("Address", supplier_address, "country")
	return country in GCC_COUNTRIES


def validate_postponed_import_vat(doc) -> None:
	if doc.get("uae_is_postponed_import_vat") and not doc.get("uae_is_import_of_goods"):
		frappe.throw(
			_("Postponed Import VAT can only be checked when Import of Goods is also checked."),
			title=_("Invalid Postponed Import VAT"),
		)
