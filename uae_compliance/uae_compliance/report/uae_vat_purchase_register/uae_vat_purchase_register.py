import frappe
from frappe import _

from uae_compliance.uae_compliance.utils.vat_return.apportionment import (
	get_period_supplies,
	get_recovery_ratio,
)
from uae_compliance.uae_compliance.utils.vat_return.group import get_group_rows
from uae_compliance.uae_compliance.utils.vat_return.sections.purchase_boxes import (
	ORDINARY,
	POSTPONED_IMPORT,
	REVERSE_CHARGE,
	classify_purchase_row,
	get_recoverable_vat,
)

# The box where each kind of purchase row is declared, and where its VAT is recovered.
BOX_BY_BUCKET = {ORDINARY: "9", REVERSE_CHARGE: "3 / 10", POSTPONED_IMPORT: "6 / 10"}


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
		{"label": _("Box"), "fieldname": "box", "fieldtype": "Data", "width": 70},
		{
			"label": _("Invoice"),
			"fieldname": "invoice",
			"fieldtype": "Link",
			"options": "Purchase Invoice",
			"width": 160,
		},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{
			"label": _("Supplier"),
			"fieldname": "supplier",
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 160,
		},
		{"label": _("Supplier TRN"), "fieldname": "trn", "fieldtype": "Data", "width": 140},
		{"label": _("Return"), "fieldname": "is_return", "fieldtype": "Check", "width": 70},
		{
			"label": _("Amount"),
			"fieldname": "amount",
			"fieldtype": "Currency",
			"options": currency,
			"width": 120,
		},
		{
			"label": _("VAT Due"),
			"fieldname": "vat_due",
			"fieldtype": "Currency",
			"options": currency,
			"width": 110,
		},
		{
			"label": _("Recoverable VAT"),
			"fieldname": "recoverable_vat",
			"fieldtype": "Currency",
			"options": currency,
			"width": 130,
		},
	]


def get_data(filters) -> list[dict]:
	"""One row per invoice and box, using the same rows and classification as the UAE VAT Return.
	Rows the return does not report (zero rated, exempt, non-recoverable) are not listed."""
	rows = get_group_rows("Purchase Invoice", filters.company, filters.from_date, filters.to_date)
	if not rows:
		return []

	invoices = {
		invoice.name: invoice
		for invoice in frappe.get_all(
			"Purchase Invoice",
			filters={"name": ["in", list({row.invoice for row in rows})]},
			fields=["name", "posting_date", "supplier"],
		)
	}
	trns = dict(
		frappe.get_all(
			"Supplier",
			filters={"name": ["in", list({invoice.supplier for invoice in invoices.values()})]},
			fields=["name", "uae_trn"],
			as_list=True,
		)
	)

	# Residual input VAT is recovered at the period's ratio, taken from the same sales rows the return uses.
	sales_rows = get_group_rows("Sales Invoice", filters.company, filters.from_date, filters.to_date)
	recovery_ratio = get_recovery_ratio(*get_period_supplies(sales_rows))

	grouped: dict[tuple[str, str], dict] = {}
	for row in rows:
		bucket = classify_purchase_row(row)
		if not bucket:
			continue

		invoice = invoices[row.invoice]
		entry = grouped.setdefault(
			(row.invoice, bucket),
			{
				"box": BOX_BY_BUCKET[bucket],
				"invoice": row.invoice,
				"posting_date": invoice.posting_date,
				"supplier": invoice.supplier,
				"trn": trns.get(invoice.supplier) or "",
				"is_return": row.is_return,
				"amount": 0.0,
				"vat_due": 0.0,
				"recoverable_vat": 0.0,
			},
		)
		entry["amount"] += row.base_net_amount or 0
		entry["vat_due"] += (row.output_vat_amount or 0) if bucket != ORDINARY else 0
		entry["recoverable_vat"] += get_recoverable_vat(row, recovery_ratio)

	return sorted(grouped.values(), key=lambda entry: (entry["box"], entry["posting_date"], entry["invoice"]))
