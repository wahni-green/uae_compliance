import frappe
from frappe import _

from uae_compliance.uae_compliance.einvoice import reconciliation as recon
from uae_compliance.uae_compliance.utils.company import is_uae_company

STATUSES = ("", "Matched", "Mismatch", "Only Received", "Only in Books", "Ignored")
ONLY_RECEIVED = "Only Received"
ONLY_BOOKS = "Only in Books"
IGNORED = "Ignored"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	return get_columns(), get_data(filters)


def validate_filters(filters) -> None:
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are mandatory"))
	if not is_uae_company(filters.company):
		frappe.throw(_("{0} is not a UAE company.").format(filters.company))


def get_columns() -> list[dict]:
	def money(label, fieldname):
		return {"label": label, "fieldname": fieldname, "fieldtype": "Float", "precision": 2, "width": 110}

	return [
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Data", "width": 170},
		{
			"label": _("E-Invoice"),
			"fieldname": "received",
			"fieldtype": "Link",
			"options": "UAE E-Invoice Log",
			"width": 130,
		},
		{"label": _("Number"), "fieldname": "received_number", "fieldtype": "Data", "width": 120},
		{"label": _("Date"), "fieldname": "received_date", "fieldtype": "Date", "width": 95},
		money(_("Taxable (E-Invoice)"), "received_taxable"),
		money(_("VAT (E-Invoice)"), "received_tax"),
		{
			"label": _("Purchase Invoice"),
			"fieldname": "invoice",
			"fieldtype": "Link",
			"options": "Purchase Invoice",
			"width": 150,
		},
		{"label": _("Bill No"), "fieldname": "bill_no", "fieldtype": "Data", "width": 120},
		{"label": _("Bill Date"), "fieldname": "bill_date", "fieldtype": "Date", "width": 95},
		money(_("Taxable (Books)"), "book_taxable"),
		money(_("VAT (Books)"), "book_tax"),
		{"label": _("Differences"), "fieldname": "differences", "fieldtype": "Data", "width": 170},
	]


def get_data(filters) -> list[dict]:
	company, from_date, to_date = filters.company, filters.from_date, filters.to_date
	wanted = filters.get("status") or ""
	rows = []

	received_by_name = {r["name"]: r for r in recon.get_received(company, from_date, to_date, matched=None)}
	books_by_name = {b["name"]: b for b in recon.get_books(company, from_date, to_date, status=None)}

	# Pairs that are linked.
	linked_books = {}
	for r in received_by_name.values():
		if r["link"]:
			book = books_by_name.get(r["link"]) or _book(r["link"], company)
			if book:
				linked_books[book["name"]] = book
				rows.append(_row(r["match_status"] or "Matched", r, book))

	# What is not linked: ignored, then likely pairs (mismatches), then the rest.
	open_received = [r for r in received_by_name.values() if not r["link"]]
	open_books = [b for b in books_by_name.values() if b["name"] not in linked_books]

	for r in open_received:
		if r["action"] == recon.ACTION_IGNORE:
			rows.append(_row(IGNORED, r, None))

	for b in open_books:
		if b["status"] == recon.STATUS_IGNORED:
			rows.append(_row(IGNORED, None, b))

	candidates_received = [r for r in open_received if not r["action"]]
	candidates_books = [b for b in open_books if not b["status"]]
	pairs = recon.match_pairs(candidates_received, candidates_books, recon.MISMATCH_RULES)
	paired_received = {r["name"] for r, _b, _s in pairs}
	paired_books = {b["name"] for _r, b, _s in pairs}
	rows += [_row(status, r, b) for r, b, status in pairs]

	rows += [_row(ONLY_RECEIVED, r, None) for r in candidates_received if r["name"] not in paired_received]
	rows += [_row(ONLY_BOOKS, None, b) for b in candidates_books if b["name"] not in paired_books]

	if wanted == "Matched":
		rows = [
			r for r in rows if r["status"] in (recon.MATCH_EXACT, recon.MATCH_SUGGESTED, recon.MATCH_MANUAL)
		]
	elif wanted:
		rows = [r for r in rows if r["status"] == wanted]
	else:
		rows = [r for r in rows if r["status"] != IGNORED]

	# Filtered on the English names; translated only for display.
	for row in rows:
		row["status"] = _(row["status"])

	return rows


def _book(name: str, company: str):
	"""A Purchase Invoice linked to a received e-invoice but posted outside the period."""
	posted = frappe.db.get_value("Purchase Invoice", name, "posting_date")
	if not posted:
		return None

	books = recon.get_books(company, posted, posted, status=None)
	return next((b for b in books if b["name"] == name), None)


def _row(status: str, received: dict | None, book: dict | None) -> dict:
	row = {"status": status}
	if received:
		row.update(
			supplier=received["party_name"],
			received=received["name"],
			received_number=received["number"],
			received_date=received["date"],
			received_taxable=received["taxable"],
			received_tax=received["tax"],
		)

	if book:
		row.update(
			supplier=row.get("supplier") or book.get("supplier_name"),
			invoice=book["name"],
			bill_no=book["bill_no"],
			bill_date=book["date"],
			book_taxable=book["taxable"],
			book_tax=book["tax"],
		)

	if received and book:
		row["differences"] = recon.get_differences(received, book)

	return row
