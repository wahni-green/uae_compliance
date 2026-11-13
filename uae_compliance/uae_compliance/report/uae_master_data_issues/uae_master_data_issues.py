"""Customers and addresses saved before the e-invoice rules, which now refuse them on the next save.
Nothing is changed: this lists what the data team has to correct."""

import frappe
from frappe import _

from uae_compliance.uae_compliance.utils.company import UAE

# Spellings of the country that are not the country (rule: the invoice looks like an export).
COUNTRY_ALIASES = ("UAE", "U.A.E", "U.A.E.", "Emirates", "United Arab Emirate")


def execute(filters=None):
	return get_columns(), get_data()


def get_columns() -> list[dict]:
	return [
		{
			"label": _("Document Type"),
			"fieldname": "document_type",
			"fieldtype": "Link",
			"options": "DocType",
			"width": 130,
		},
		{
			"label": _("Document"),
			"fieldname": "document",
			"fieldtype": "Dynamic Link",
			"options": "document_type",
			"width": 220,
		},
		{"label": _("Issue"), "fieldname": "issue", "fieldtype": "Data", "width": 420},
	]


def get_data() -> list[dict]:
	return [*get_customer_issues(), *get_address_issues()]


def get_customer_issues() -> list[dict]:
	return [
		*_rows(
			"Customer",
			{"uae_legal_registration_id": ["is", "set"], "uae_legal_registration_type": ["is", "not set"]},
			_("A Legal Registration ID is entered but the Legal Registration Type is not."),
		),
		*_rows(
			"Customer",
			{"uae_legal_registration_type": "Trade License", "uae_licence_authority": ["is", "not set"]},
			_("The Legal Registration Type is Trade License but the Licence Issuing Authority is not set."),
		),
		*_rows(
			"Customer",
			{"uae_legal_registration_type": "Passport", "uae_passport_country": ["is", "not set"]},
			_("The Legal Registration Type is Passport but the Passport Issuing Country is not set."),
		),
	]


def get_address_issues() -> list[dict]:
	wrong_countries = get_wrong_country_names()
	return [
		*_rows(
			"Address",
			{"country": UAE, "uae_emirate": ["is", "not set"]},
			_("The address is in the UAE but the Emirate is not set."),
		),
		*(
			_rows(
				"Address",
				{"country": ["in", wrong_countries]},
				_("The country is not written as {0}.").format(UAE),
			)
			if wrong_countries
			else []
		),
	]


def get_wrong_country_names() -> list[str]:
	"""Country records that stand for the UAE under another name."""
	by_code = frappe.get_all("Country", filters={"code": "ae", "name": ["!=", UAE]}, pluck="name")
	by_alias = frappe.get_all("Country", filters={"name": ["in", COUNTRY_ALIASES]}, pluck="name")
	return sorted({*by_code, *by_alias} - {UAE})


def _rows(doctype: str, filters: dict, issue: str) -> list[dict]:
	return [
		{"document_type": doctype, "document": name, "issue": issue}
		for name in frappe.get_all(doctype, filters=filters, pluck="name", order_by="name")
	]
