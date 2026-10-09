import frappe
from frappe import _
from frappe.utils import flt

from uae_compliance.uae_compliance.constants import DEFAULT_VAT_CATEGORY
from uae_compliance.uae_compliance.constants.vat_return import REPORTABLE_VAT_CATEGORIES
from uae_compliance.uae_compliance.utils.tax_account import (
	get_item_wise_vat_amounts,
	is_input_vat_account,
	is_output_vat_account,
)

_PARENT_FIELDS = {
	"Sales Invoice": ("uae_emirate", "uae_is_export", "uae_tourist_refund"),
	"Purchase Invoice": (
		"uae_is_reverse_charge",
		"uae_is_gcc_supplier",
		"uae_is_import_of_goods",
		"uae_is_postponed_import_vat",
	),
}

_CHILD_FIELDS = {"Purchase Invoice": ("uae_input_tax_not_recoverable",)}


def get_invoice_rows(doctype: str, company: str, from_date, to_date) -> list:
	"""One dict per submitted Sales/Purchase Invoice Item row in [from_date, to_date] for `company`,
	with its parent's classification flags, its resolved VAT category and its share of the VAT
	posted to the company's Output and Input VAT accounts. Every section function filters and sums
	these rows. Rows are in company currency (AED), and credit notes and returns carry negative
	values, so they net into the box they belong to (the VAT 201 form asks for reductions due to
	credit notes to be included in the amount and VAT columns).

	Out of Scope rows are left out: they are not reported on the return."""
	# get_all bypasses per-document permissions to be able to sum every invoice in the period, so
	# the one thing gated on the caller's own access, the Company, is checked explicitly.
	frappe.has_permission("Company", "read", doc=company, throw=True)

	invoices = frappe.get_all(
		doctype,
		filters={
			"company": company,
			"posting_date": ["between", [from_date, to_date]],
			"docstatus": 1,
		},
		fields=["name", "is_return", *_PARENT_FIELDS[doctype]],
	)
	if not invoices:
		return []

	invoices_by_name = {invoice.name: invoice for invoice in invoices}

	item_fields = [
		"name",
		"parent",
		"item_code",
		"uae_vat_category",
		"item_tax_template",
		"base_net_amount",
		*_CHILD_FIELDS.get(doctype, ()),
	]
	legacy_flags = [
		fieldname
		for fieldname in ("is_zero_rated", "is_exempt")
		if frappe.db.has_column(f"{doctype} Item", fieldname)
	]
	items = frappe.get_all(
		f"{doctype} Item",
		filters={"parent": ["in", list(invoices_by_name)]},
		fields=[*item_fields, *legacy_flags],
	)
	if not items:
		return []

	tax_doctype = "Sales Taxes and Charges" if doctype == "Sales Invoice" else "Purchase Taxes and Charges"
	tax_rows_by_parent: dict[str, list] = {}
	for tax in frappe.get_all(
		tax_doctype,
		filters={"parent": ["in", list(invoices_by_name)]},
		fields=["parent", "account_head", "item_wise_tax_detail"],
	):
		tax_rows_by_parent.setdefault(tax.parent, []).append(tax)

	output_vat_by_parent = {
		parent: get_item_wise_vat_amounts(rows, company, is_output_vat_account)
		for parent, rows in tax_rows_by_parent.items()
	}
	input_vat_by_parent = {
		parent: get_item_wise_vat_amounts(rows, company, is_input_vat_account)
		for parent, rows in tax_rows_by_parent.items()
	}

	resolver = CategoryResolver()
	for item in items:
		item.category = resolver.resolve(item)

	_validate_unambiguous_item_codes(items)

	# item_wise_tax_detail is keyed by item code, not row. Rows sharing an item code (which share a
	# VAT treatment, checked above) split the combined amount by their share of the net amount.
	net_by_key: dict[tuple[str, str], float] = {}
	for item in items:
		key = (item.parent, item.item_code)
		net_by_key[key] = net_by_key.get(key, 0) + flt(item.base_net_amount)

	rows = []
	for item in items:
		if item.category not in REPORTABLE_VAT_CATEGORIES:
			continue

		invoice = invoices_by_name[item.parent]
		total_net = net_by_key[(item.parent, item.item_code)]
		share = flt(item.base_net_amount) / total_net if total_net else 0

		row = frappe._dict(item)
		row.invoice = item.parent
		row.is_return = bool(invoice.is_return)
		row.output_vat_amount = output_vat_by_parent.get(item.parent, {}).get(item.item_code, 0) * share
		row.input_vat_amount = input_vat_by_parent.get(item.parent, {}).get(item.item_code, 0) * share
		for field in _PARENT_FIELDS[doctype]:
			row[field] = invoice.get(field)
		rows.append(row)

	return rows


class CategoryResolver:
	"""The VAT category of an item row. A row saved by this app carries its own. Rows from before
	the app was installed fall back, in order, to the category of the row's Item Tax Template, the
	ERPNext zero rated / exempt flags on the row, the Item's own category, then Standard Rated."""

	def __init__(self):
		self._template: dict[str, str | None] = {}
		self._item: dict[str, str | None] = {}

	def resolve(self, row) -> str:
		if row.get("uae_vat_category"):
			return row.uae_vat_category

		template = row.get("item_tax_template")
		if template:
			if template not in self._template:
				self._template[template] = frappe.db.get_value(
					"Item Tax Template", template, "uae_vat_category"
				)
			if self._template[template]:
				return self._template[template]

		if row.get("is_zero_rated") and not row.get("is_exempt"):
			return "Zero Rated"
		if row.get("is_exempt") and not row.get("is_zero_rated"):
			return "Exempt"

		item_code = row.get("item_code")
		if item_code:
			if item_code not in self._item:
				self._item[item_code] = frappe.db.get_value("Item", item_code, "uae_vat_category")
			if self._item[item_code]:
				return self._item[item_code]

		return DEFAULT_VAT_CATEGORY


def _validate_unambiguous_item_codes(items) -> None:
	"""Refuse to guess how to split the VAT of one item code that appears with different VAT
	treatment on the same invoice. Such invoices are rejected when saved, so this only catches data
	from before that check existed. A return that silently omits transactions is worse than one
	that fails loudly."""
	configs: dict[tuple[str, str], set] = {}
	for item in items:
		configs.setdefault((item.parent, item.item_code), set()).add((item.category, item.item_tax_template))

	for (parent, item_code), item_configs in configs.items():
		if len(item_configs) > 1:
			frappe.throw(
				_(
					"{0}: item {1} appears on more than one row with inconsistent VAT treatment (VAT"
					" Category and/or Item Tax Template differ). Its VAT cannot be split across rows for a"
					" VAT return. Give each combination its own Item Code before generating a return for"
					" this period."
				).format(parent, frappe.bold(item_code)),
				title=_("Ambiguous VAT Category"),
			)


def summarize_box(rows: list, vat_amount_field: str = "output_vat_amount") -> dict:
	"""Sum rows into the amount / VAT / adjustment shape of a VAT 201 box. Returns and credit notes
	are already negative and net into the amount and VAT. The adjustment column is reserved for
	adjustments that are not transactions (bad debt relief, apportionment) and starts at zero."""
	return {
		"amount": sum(flt(row.base_net_amount) for row in rows),
		"vat_amount": sum(flt(row.get(vat_amount_field)) for row in rows),
		"adjustment": 0.0,
	}
