import hashlib

import frappe
from frappe import _
from frappe.utils import flt

from uae_compliance.uae_compliance.utils.tax_account import (
	get_input_vat_account,
	get_output_vat_account,
)
from uae_compliance.uae_compliance.utils.vat_return import get_invoice_rows

_PARTY = {"Sales Invoice": ("Customer", "customer"), "Purchase Invoice": ("Supplier", "supplier")}


def get_return_companies(company: str) -> list[str]:
	"""The companies a company's VAT return covers. A tax group files one return, through its
	representative member, covering every member; a member that is not the representative files
	nothing of its own. Any other company covers itself."""
	group = frappe.db.get_value("Company", company, "uae_tax_group")
	if not group:
		return [company]

	tax_group = frappe.get_doc("UAE Tax Group", group)
	if tax_group.representative_member != company:
		frappe.throw(
			_(
				"{0} is a member of the tax group {1}. The group's VAT return is filed by its representative member, {2}."
			).format(company, group, tax_group.representative_member),
			title=_("Member of a Tax Group"),
		)

	return [row.company for row in tax_group.members]


def get_return_owner(company: str) -> str:
	"""The company whose VAT return reports this company's transactions: the representative
	member for a member of a tax group, the company itself otherwise."""
	group = frappe.db.get_value("Company", company, "uae_tax_group")
	if not group:
		return company

	return frappe.db.get_value("UAE Tax Group", group, "representative_member") or company


def get_group_rows(doctype: str, company: str, from_date, to_date) -> list:
	"""The invoice rows of a VAT return, covering every company of a tax group and leaving out
	supplies between the group's own members, which are disregarded for VAT. A member shows up in the
	other's books as an internal customer or supplier that represents it."""
	companies = get_return_companies(company)

	missing = [name for name in companies if not get_output_vat_account(name)]
	if missing:
		frappe.throw(
			_("Configure the Output VAT Account in UAE Compliance Settings for: {0}").format(
				", ".join(missing)
			),
			title=_("VAT Accounts Not Configured"),
		)

	rows = []
	for name in companies:
		company_rows = get_invoice_rows(doctype, name, from_date, to_date)
		# Without an Input VAT account the recoverable VAT of a company's purchases would silently be zero.
		if company_rows and doctype == "Purchase Invoice" and not get_input_vat_account(name):
			frappe.throw(
				_(
					"{0} has purchases in this period, so its Input VAT Account must be configured in UAE Compliance Settings."
				).format(name),
				title=_("VAT Accounts Not Configured"),
			)

		rows.extend(company_rows)

	if len(companies) > 1:
		rows = exclude_intra_group(rows, doctype, companies)

	return rows


def get_scope(company: str) -> tuple[str, ...]:
	"""The companies a return generated for `company` covers right now, as a sorted tuple. A member that
	is not the representative has no return of its own."""
	group = frappe.db.get_value("Company", company, "uae_tax_group")
	if not group:
		return (company,)

	tax_group = frappe.get_doc("UAE Tax Group", group)
	if tax_group.representative_member != company:
		return (f"member of {group}",)

	return tuple(sorted(row.company for row in tax_group.members))


def get_internal_parties(party_doctype: str, companies: list[str]) -> set[str]:
	"""Customers or suppliers that stand for one of the companies, i.e. the other members of a group."""
	return set(frappe.get_all(party_doctype, filters={"represents_company": ["in", companies]}, pluck="name"))


def is_intra_group(company: str, party_doctype: str, party: str) -> bool:
	"""Whether a sale to a customer or a purchase from a supplier is between two members of the
	company's tax group."""
	group = frappe.db.get_value("Company", company, "uae_tax_group")
	if not group or not party:
		return False

	members = [row.company for row in frappe.get_doc("UAE Tax Group", group).members]
	return frappe.db.get_value(party_doctype, party, "represents_company") in members


def exclude_intra_group(rows: list, doctype: str, companies: list[str]) -> list:
	party_doctype, party_field = _PARTY[doctype]
	internal = get_internal_parties(party_doctype, companies)
	return [row for row in rows if row.get(party_field) not in internal]


def get_data_fingerprint(company: str, from_date, to_date) -> str:
	"""A fingerprint of everything a return of the period is built from: the submitted invoices and
	VAT adjustments of the companies it covers, with their amounts. It changes when a document is
	submitted, cancelled or amended in the period, so a return generated earlier can be seen to be out
	of date."""
	companies = get_return_companies(company)
	parts = []
	for doctype, fields in (
		("Sales Invoice", ["name", "base_grand_total", "base_total_taxes_and_charges"]),
		("Purchase Invoice", ["name", "base_grand_total", "base_total_taxes_and_charges"]),
		("UAE VAT Adjustment", ["name", "amount", "vat_amount"]),
	):
		rows = frappe.get_all(
			doctype,
			filters={
				"company": ["in", companies],
				"docstatus": 1,
				"posting_date": ["between", [from_date, to_date]],
			},
			fields=fields,
			order_by="name asc",
			limit_page_length=0,
			as_list=True,
		)
		parts.append(f"{doctype}:{rows}")

	# The rows the boxes are built from, with their resolved category and VAT: an invoice from before
	# the app takes its category from its Item Tax Template or Item, so changing those moves it
	# between boxes without touching the invoice.
	for doctype in ("Sales Invoice", "Purchase Invoice"):
		for name in companies:
			rows = get_invoice_rows(doctype, name, from_date, to_date)
			parts.append(
				f"{doctype}:{name}:"
				+ repr(
					sorted(
						(
							row.name,
							row.category,
							round(flt(row.base_net_amount), 2),
							round(flt(row.output_vat_amount), 2),
							round(flt(row.input_vat_amount), 2),
							bool(row.get("uae_input_tax_not_recoverable")),
						)
						for row in rows
					)
				)
			)

	return hashlib.sha256("|".join(parts).encode()).hexdigest()
