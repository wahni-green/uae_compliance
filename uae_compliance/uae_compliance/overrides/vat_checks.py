import frappe
from frappe import _

from uae_compliance.uae_compliance.constants import NO_TAX_VAT_CATEGORIES
from uae_compliance.uae_compliance.utils.tax_account import (
	get_item_wise_vat_rates,
	is_input_vat_account,
	is_output_vat_account,
)
from uae_compliance.uae_compliance.utils.vat_category import get_item_tax_template_category


def validate_vat_category_tax_consistency(doc) -> None:
	"""A Zero Rated / Exempt / Out of Scope row must not carry VAT, and a row's category must agree
	with its Item Tax Template. Reads rates from item_wise_tax_detail (percentages, so currency
	agnostic). Only that direction is checked: Standard Rated at a net 0% is a valid outcome of many
	ordinary tax templates."""
	# Sales charge VAT on the Output account; purchases bear it on the Input account.
	is_vat_account = is_input_vat_account if doc.doctype == "Purchase Invoice" else is_output_vat_account
	charged_rates = get_item_wise_vat_rates(doc.get("taxes") or [], doc.get("company"), is_vat_account)
	categories_by_item = _categories_by_item_code(doc.get("items") or [])

	for row in doc.get("items", []):
		category = row.get("uae_vat_category")

		template_category = get_item_tax_template_category(row.get("item_tax_template"))
		if template_category and template_category != category:
			frappe.throw(
				_(
					"Row #{0}: item {1} is marked {2} but its Item Tax Template ({3}) is set up for {4}."
				).format(
					row.idx, frappe.bold(row.item_code), category, row.item_tax_template, template_category
				),
				title=_("VAT Category Mismatch"),
			)

		if category not in NO_TAX_VAT_CATEGORIES:
			continue

		# item_wise_tax_detail is keyed by item code, so rows sharing a code with different
		# categories can't be told apart here (they are rejected separately below).
		if len(categories_by_item[row.item_code]) > 1:
			continue

		rate = charged_rates.get(row.item_code, 0)
		if rate:
			frappe.throw(
				_("Row #{0}: item {1} is marked {2} but a {3}% VAT rate was applied to it.").format(
					row.idx, frappe.bold(row.item_code), category, rate
				),
				title=_("VAT Category Mismatch"),
			)


def validate_no_mixed_vat_category_per_item_code(doc) -> None:
	"""item_wise_tax_detail is keyed by item code, not row, so VAT can't later be split per row if
	one item code appears with different VAT Category or Item Tax Template. Block it at the source
	rather than misattribute VAT between VAT 201 boxes."""
	configs: dict[str, set] = {}
	for row in doc.get("items") or []:
		configs.setdefault(row.item_code, set()).add(
			(row.get("uae_vat_category"), row.get("item_tax_template"))
		)

	for item_code, item_configs in configs.items():
		if len(item_configs) > 1:
			categories = sorted({category or "" for category, _template in item_configs})
			frappe.throw(
				_(
					"Item {0} appears on more than one row with inconsistent VAT treatment (VAT Category"
					" and/or Item Tax Template differ: {1}). Use the same VAT Category and Item Tax"
					" Template throughout, or a distinct Item Code per combination."
				).format(frappe.bold(item_code), ", ".join(categories)),
				title=_("VAT Category Mismatch"),
			)


def _categories_by_item_code(item_rows) -> dict[str, set]:
	categories: dict[str, set] = {}
	for row in item_rows:
		categories.setdefault(row.item_code, set()).add(row.get("uae_vat_category"))

	return categories
