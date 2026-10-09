import frappe
from frappe import _

from uae_compliance.uae_compliance.constants.vat_return import EMIRATE_BOX_CODES
from uae_compliance.uae_compliance.utils.vat_return.group import get_group_rows
from uae_compliance.uae_compliance.utils.vat_return.sections.sales_boxes import (
	SALES_BOX_BY_CATEGORY,
	get_tourist_refunds_by_invoice,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	return get_columns(), get_data(filters)


def validate_filters(filters) -> None:
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are mandatory"))


def get_columns() -> list[dict]:
	currency = "Company:company:default_currency"
	return [
		{"label": _("Box"), "fieldname": "box", "fieldtype": "Data", "width": 60},
		{
			"label": _("Invoice"),
			"fieldname": "invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 160,
		},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 160,
		},
		{"label": _("Customer TRN"), "fieldname": "trn", "fieldtype": "Data", "width": 140},
		{"label": _("VAT Category"), "fieldname": "category", "fieldtype": "Data", "width": 110},
		{"label": _("Emirate"), "fieldname": "emirate", "fieldtype": "Data", "width": 110},
		{"label": _("Return"), "fieldname": "is_return", "fieldtype": "Check", "width": 70},
		{
			"label": _("Amount"),
			"fieldname": "amount",
			"fieldtype": "Currency",
			"options": currency,
			"width": 120,
		},
		{
			"label": _("VAT"),
			"fieldname": "vat_amount",
			"fieldtype": "Currency",
			"options": currency,
			"width": 110,
		},
	]


def get_data(filters) -> list[dict]:
	"""One row per invoice and VAT 201 box, using the same rows and the same box assignment as the
	UAE VAT Return, so the register always agrees with the return it supports."""
	rows = get_group_rows("Sales Invoice", filters.company, filters.from_date, filters.to_date)
	if not rows:
		return []

	invoices = {
		invoice.name: invoice
		for invoice in frappe.get_all(
			"Sales Invoice",
			filters={"name": ["in", list({row.invoice for row in rows})]},
			fields=["name", "posting_date", "customer"],
		)
	}
	trns = dict(
		frappe.get_all(
			"Customer",
			filters={"name": ["in", list({invoice.customer for invoice in invoices.values()})]},
			fields=["name", "uae_trn"],
			as_list=True,
		)
	)

	grouped: dict[tuple[str, str], dict] = {}
	for row in rows:
		box = (
			EMIRATE_BOX_CODES.get(row.uae_emirate, "")
			if row.category == "Standard Rated"
			else SALES_BOX_BY_CATEGORY[row.category]
		)
		invoice = invoices[row.invoice]
		entry = grouped.setdefault(
			(row.invoice, box),
			{
				"box": box,
				"invoice": row.invoice,
				"posting_date": invoice.posting_date,
				"customer": invoice.customer,
				"trn": trns.get(invoice.customer) or "",
				"category": row.category,
				"emirate": row.uae_emirate or "",
				"is_return": row.is_return,
				"amount": 0.0,
				"vat_amount": 0.0,
			},
		)
		entry["amount"] += row.reported_amount or 0
		entry["vat_amount"] += row.output_vat_amount or 0

	# Tax refunded to tourists reduces the VAT due in box 2: one negative row per invoice.
	for invoice_name, refund in get_tourist_refunds_by_invoice(rows).items():
		invoice = invoices[invoice_name]
		grouped[(invoice_name, "2")] = {
			"box": "2",
			"invoice": invoice_name,
			"posting_date": invoice.posting_date,
			"customer": invoice.customer,
			"trn": trns.get(invoice.customer) or "",
			"category": "",
			"emirate": "",
			"is_return": 0,
			"amount": 0.0,
			"vat_amount": -refund,
		}

	return sorted(grouped.values(), key=lambda entry: (entry["box"], entry["posting_date"], entry["invoice"]))
