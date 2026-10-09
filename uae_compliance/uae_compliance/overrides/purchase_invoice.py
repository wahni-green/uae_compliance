import frappe
from frappe import _
from frappe.utils import flt

from uae_compliance.uae_compliance.constants import (
	DEFAULT_VAT_CATEGORY,
	IMPORT_OF_GOODS_TYPE,
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

	if doc.get("uae_reverse_charge_type") == METAL_SCRAP_TYPE and not doc.get("uae_rc_declaration"):
		frappe.throw(
			_(
				"Metal scrap reverse charge requires the recipient's declaration to be on file before"
				" the supply date. Tick Recipient Declaration on File once obtained."
			),
			title=_("Declaration Required"),
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
