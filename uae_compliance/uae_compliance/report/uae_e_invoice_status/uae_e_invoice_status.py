"""Sales Invoices that have to be e-invoiced and where each one stands, so the ones that need
attention (Invalid, Rejected, Failed, or never sent) can be found and fixed."""

import frappe
from frappe import _
from frappe.query_builder import DocType

NOT_SENT = "Not Sent"


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
	return [
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
		{
			"label": _("Amount"),
			"fieldname": "grand_total",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
		{
			"label": _("E-Invoice Log"),
			"fieldname": "log",
			"fieldtype": "Link",
			"options": "UAE E-Invoice Log",
			"width": 140,
		},
		{"label": _("Attempts"), "fieldname": "attempts", "fieldtype": "Int", "width": 80},
		{"label": _("Last Attempt"), "fieldname": "last_attempt_on", "fieldtype": "Datetime", "width": 150},
		{"label": _("Next Attempt"), "fieldname": "next_attempt_on", "fieldtype": "Datetime", "width": 150},
		{"label": _("Cleared On"), "fieldname": "cleared_on", "fieldtype": "Datetime", "width": 150},
		{"label": _("Detail"), "fieldname": "detail", "fieldtype": "Data", "width": 300},
		{
			"label": _("Currency"),
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		},
	]


def get_data(filters) -> list[dict]:
	invoice = DocType("Sales Invoice")
	log = DocType("UAE E-Invoice Log")

	query = (
		frappe.qb.from_(invoice)
		.left_join(log)
		.on((log.reference_doctype == "Sales Invoice") & (log.reference_name == invoice.name))
		.select(
			invoice.name.as_("invoice"),
			invoice.posting_date,
			invoice.customer,
			invoice.grand_total,
			invoice.currency,
			log.status,
			log.name.as_("log"),
			log.attempts,
			log.last_attempt_on,
			log.next_attempt_on,
			log.cleared_on,
			log.errors,
			log.status_detail,
		)
		.where(invoice.docstatus == 1)
		.where(invoice.uae_einvoice_applicable == 1)
		.where(invoice.company == filters.company)
		.where(invoice.posting_date.between(filters.from_date, filters.to_date))
		.orderby(invoice.posting_date, order=frappe.qb.desc)
		.orderby(invoice.name, order=frappe.qb.desc)
	)
	query = add_optional_filters(query, filters, invoice, log)

	return [with_detail(row) for row in query.run(as_dict=True)]


def add_optional_filters(query, filters, invoice, log):
	if filters.get("customer"):
		query = query.where(invoice.customer == filters.customer)

	if filters.get("status") == NOT_SENT:
		query = query.where(log.name.isnull())
	elif filters.get("status"):
		query = query.where(log.status == filters.status)

	return query


def with_detail(row: dict) -> dict:
	"""The first error, or the provider's message when there is none. The full text is on the log."""
	errors, status_detail = row.pop("errors"), row.pop("status_detail")
	detail = errors or status_detail or ""
	row["detail"] = detail.splitlines()[0] if detail else ""
	row["status"] = row["status"] or NOT_SENT

	return row
