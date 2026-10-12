"""Purchase reconciliation: matching the e-invoices a company received (inbound UAE E-Invoice Logs)
with its Purchase Invoices, so that input VAT is claimed on invoices the supplier reported.

Matching runs per supplier over documents that are not matched yet, one rule after another, and each
document is claimed once. The first three rules (exact, and two suggestions) are stored as links; the
two mismatch rules only point out a likely pair, which the user confirms by linking it."""

from datetime import timedelta
from difflib import SequenceMatcher

import frappe
from frappe import _
from frappe.utils import flt, getdate

from uae_compliance.uae_compliance.constants.einvoice import DIRECTION_INBOUND
from uae_compliance.uae_compliance.utils.company import is_uae_company
from uae_compliance.uae_compliance.utils.tax_account import is_input_vat_account

LOG = "UAE E-Invoice Log"
INVOICE = "Purchase Invoice"

# The taxable amount and the VAT together may differ by this much (AED) and still count as equal.
TOLERANCE = 1.0
# Bill dates this many days apart still count as close.
DATE_WINDOW_DAYS = 10
# A fuzzy bill number needs at least this similarity.
FUZZY_RATIO = 0.9

MATCH_EXACT = "Exact Match"
MATCH_SUGGESTED = "Suggested Match"
MATCH_MANUAL = "Manual Match"
MISMATCH = "Mismatch"

STATUS_MATCHED = "Match Found"
STATUS_IGNORED = "Ignored"
ACTION_IGNORE = "Ignore"


# ---------------------------------------------------------------- comparing


def normalize_bill_no(value: str | None) -> str:
	"""Upper case, letters and digits only, and no leading zeros, so that 'INV/0012' and 'inv-12'
	are the same number."""
	text = "".join(ch for ch in (value or "").upper() if ch.isalnum())
	return text.lstrip("0") or text


def bill_numbers_match(a: str | None, b: str | None) -> bool:
	return bool(normalize_bill_no(a)) and normalize_bill_no(a) == normalize_bill_no(b)


def bill_numbers_are_close(a: str | None, b: str | None) -> bool:
	"""The same number written differently: one inside the other (a prefix or a year added) or very
	similar."""
	x, y = normalize_bill_no(a), normalize_bill_no(b)
	if not x or not y:
		return False

	if x == y:
		return True

	short, long = sorted((x, y), key=len)
	if len(short) >= 3 and short in long:
		return True

	return SequenceMatcher(None, x, y).ratio() >= FUZZY_RATIO


def dates_are_close(a, b) -> bool:
	if not a or not b:
		return False

	return abs((getdate(a) - getdate(b)).days) <= DATE_WINDOW_DAYS


def amounts_are_close(received: dict, book: dict) -> bool:
	"""The taxable amount and the VAT, taken together, differ by no more than the tolerance. Taking
	them together stops several small differences passing one by one."""
	difference = abs(abs(flt(received["taxable"])) - abs(flt(book["taxable"]))) + abs(
		abs(flt(received["tax"])) - abs(flt(book["tax"]))
	)
	return difference <= TOLERANCE + 1e-9


# The rules in order. Each takes a received document and a Purchase Invoice of the same supplier,
# currency and kind (invoice or credit note).
STORED_RULES = (
	(
		MATCH_EXACT,
		lambda r, b: (
			bill_numbers_match(r["number"], b["bill_no"])
			and getdate(r["date"]) == getdate(b["date"])
			and amounts_are_close(r, b)
		),
	),
	(
		MATCH_SUGGESTED,
		lambda r, b: (
			bill_numbers_are_close(r["number"], b["bill_no"])
			and dates_are_close(r["date"], b["date"])
			and amounts_are_close(r, b)
		),
	),
	(
		MATCH_SUGGESTED,
		lambda r, b: bill_numbers_match(r["number"], b["bill_no"]) and amounts_are_close(r, b),
	),
)
MISMATCH_RULES = (
	(MISMATCH, lambda r, b: bill_numbers_are_close(r["number"], b["bill_no"])),
	(MISMATCH, lambda r, b: amounts_are_close(r, b) and dates_are_close(r["date"], b["date"])),
)


def match_pairs(received: list[dict], books: list[dict], rules) -> list[tuple[dict, dict, str]]:
	"""(received, book, status) pairs: rule by rule, each document claimed once."""
	pairs = []
	claimed_received, claimed_books = set(), set()
	for status, rule in rules:
		for r in received:
			if r["name"] in claimed_received:
				continue

			for b in books:
				if b["name"] in claimed_books or not _comparable(r, b):
					continue

				if rule(r, b):
					pairs.append((r, b, status))
					claimed_received.add(r["name"])
					claimed_books.add(b["name"])
					break

	return pairs


def _comparable(received: dict, book: dict) -> bool:
	return (
		received["supplier"] == book["supplier"]
		and received["currency"] == book["currency"]
		and received["is_return"] == book["is_return"]
	)


# ---------------------------------------------------------------- the documents


def get_received(company: str, from_date, to_date, matched: bool | None = False) -> list[dict]:
	"""Received e-invoices dated in the period. `matched` False gives those with no link and no
	action, True those with a link, None every one."""
	filters = {
		"company": company,
		"direction": DIRECTION_INBOUND,
		"document_date": ("between", [from_date, to_date]),
	}
	if matched is False:
		filters["link_name"] = ("is", "not set")
		filters["recon_action"] = ("is", "not set")
	elif matched is True:
		filters["link_name"] = ("is", "set")

	rows = frappe.get_all(
		LOG,
		filters=filters,
		fields=[
			"name",
			"supplier",
			"party_name",
			"document_number",
			"document_type",
			"document_date",
			"currency",
			"taxable_amount",
			"tax_amount",
			"total_amount",
			"match_status",
			"link_name",
			"recon_action",
		],
		order_by="document_date, name",
	)
	return [_received(row) for row in rows]


def _received(row) -> dict:
	return {
		"name": row.name,
		"supplier": row.supplier,
		"party_name": row.party_name,
		"number": row.document_number,
		"date": row.document_date,
		"currency": row.currency,
		"is_return": row.document_type in ("Credit Note", _("Credit Note")),
		"taxable": flt(row.taxable_amount),
		"tax": flt(row.tax_amount),
		"total": flt(row.total_amount),
		"match_status": row.match_status,
		"link": row.link_name,
		"action": row.recon_action,
	}


def get_books(company: str, from_date, to_date, status: str | None = "") -> list[dict]:
	"""Submitted Purchase Invoices of domestic suppliers posted in the period (the supplier of a
	reverse charge, GCC or import purchase sends no e-invoice). `status` filters on the
	reconciliation status; None gives every one."""
	filters = {
		"company": company,
		"docstatus": 1,
		"posting_date": ("between", [from_date, to_date]),
		"uae_is_reverse_charge": 0,
		"uae_is_gcc_supplier": 0,
		"uae_is_import_of_goods": 0,
	}
	if status is not None:
		filters["uae_reconciliation_status"] = status

	invoices = frappe.get_all(
		INVOICE,
		filters=filters,
		fields=[
			"name",
			"supplier",
			"supplier_name",
			"bill_no",
			"bill_date",
			"posting_date",
			"is_return",
			"currency",
			"net_total",
			"grand_total",
			"uae_reconciliation_status",
		],
		order_by="posting_date, name",
	)
	if not invoices:
		return []

	taxes = frappe.get_all(
		"Purchase Taxes and Charges",
		filters={"parent": ("in", [i.name for i in invoices]), "parenttype": INVOICE},
		fields=["parent", "account_head", "tax_amount", "add_deduct_tax"],
	)
	vat = {}
	for row in taxes:
		if is_input_vat_account(row.account_head, company):
			sign = -1 if row.add_deduct_tax == "Deduct" else 1
			vat[row.parent] = vat.get(row.parent, 0) + sign * flt(row.tax_amount)

	return [
		{
			"name": i.name,
			"supplier": i.supplier,
			"supplier_name": i.supplier_name,
			"bill_no": i.bill_no,
			"date": i.bill_date or i.posting_date,
			"posting_date": i.posting_date,
			"currency": i.currency,
			"is_return": bool(i.is_return),
			"taxable": flt(i.net_total),
			"tax": flt(vat.get(i.name)),
			"total": flt(i.grand_total),
			"status": i.uae_reconciliation_status,
		}
		for i in invoices
	]


# ---------------------------------------------------------------- matching and linking


def _check_company(company: str) -> None:
	if not is_uae_company(company):
		frappe.throw(_("{0} is not a UAE company.").format(company))


@frappe.whitelist()
def run_matching(company: str, from_date: str, to_date: str) -> dict:
	"""Match what is not matched yet (exact and suggested matches are stored as links). Books are taken
	from a window around the period, so that an invoice posted a few days before or after its
	e-invoice is still found."""
	_check_company(company)
	frappe.has_permission(LOG, "write", throw=True)

	padding = timedelta(days=30)
	received = get_received(company, from_date, to_date, matched=False)
	books = get_books(company, getdate(from_date) - padding, getdate(to_date) + padding)

	pairs = match_pairs(received, books, STORED_RULES)
	for r, b, status in pairs:
		_set_link(r["name"], b["name"], status)

	return {"matched": len(pairs), "received": len(received), "books": len(books)}


def _set_link(log: str, invoice: str, status: str) -> None:
	frappe.db.set_value(
		LOG,
		log,
		{"link_name": invoice, "match_status": status, "recon_action": ""},
		update_modified=False,
	)
	frappe.db.set_value(INVOICE, invoice, "uae_reconciliation_status", STATUS_MATCHED, update_modified=False)


@frappe.whitelist()
def link_documents(log: str, invoice: str) -> None:
	"""Link a received e-invoice to a Purchase Invoice by hand. Anything either was linked to is
	released first."""
	frappe.has_permission(LOG, "write", throw=True)
	frappe.has_permission(INVOICE, "write", throw=True)
	received = frappe.db.get_value(LOG, log, ["company", "direction"], as_dict=True)
	book = frappe.db.get_value(INVOICE, invoice, ["company", "docstatus"], as_dict=True)
	if not received or received.direction != DIRECTION_INBOUND:
		frappe.throw(_("{0} is not a received e-invoice.").format(log))

	if not book or book.docstatus != 1 or book.company != received.company:
		frappe.throw(_("{0} must be a submitted Purchase Invoice of {1}.").format(invoice, received.company))

	_check_company(received.company)

	unlink_documents([log])
	for other in frappe.get_all(LOG, filters={"link_name": invoice}, pluck="name"):
		unlink_documents([other])

	_set_link(log, invoice, MATCH_MANUAL)


@frappe.whitelist()
def unlink_documents(logs: str | list) -> None:
	"""Release the received e-invoices from their Purchase Invoices; both go back to unmatched and
	are matched again by the next run."""
	logs = frappe.parse_json(logs) if isinstance(logs, str) else logs
	frappe.has_permission(LOG, "write", throw=True)
	for log in logs:
		invoice = frappe.db.get_value(LOG, log, "link_name")
		frappe.db.set_value(LOG, log, {"link_name": "", "match_status": ""}, update_modified=False)
		if invoice:
			frappe.db.set_value(INVOICE, invoice, "uae_reconciliation_status", "", update_modified=False)


@frappe.whitelist()
def ignore_documents(logs: str | list | None = None, invoices: str | list | None = None) -> None:
	"""Leave received e-invoices or Purchase Invoices out of matching. A linked one has to be unlinked
	first."""
	logs = frappe.parse_json(logs) if isinstance(logs, str) else logs or []
	invoices = frappe.parse_json(invoices) if isinstance(invoices, str) else invoices or []
	frappe.has_permission(LOG, "write", throw=True)
	for log in logs:
		if frappe.db.get_value(LOG, log, "link_name"):
			frappe.throw(_("{0} is linked. Unlink it before ignoring it.").format(log))

		frappe.db.set_value(LOG, log, "recon_action", ACTION_IGNORE, update_modified=False)

	for invoice in invoices:
		if frappe.db.get_value(INVOICE, invoice, "uae_reconciliation_status") == STATUS_MATCHED:
			frappe.throw(_("{0} is linked. Unlink it before ignoring it.").format(invoice))

		frappe.db.set_value(
			INVOICE, invoice, "uae_reconciliation_status", STATUS_IGNORED, update_modified=False
		)


@frappe.whitelist()
def restore_documents(logs: str | list | None = None, invoices: str | list | None = None) -> None:
	"""Take ignored documents back into matching."""
	logs = frappe.parse_json(logs) if isinstance(logs, str) else logs or []
	invoices = frappe.parse_json(invoices) if isinstance(invoices, str) else invoices or []
	frappe.has_permission(LOG, "write", throw=True)
	for log in logs:
		frappe.db.set_value(LOG, log, "recon_action", "", update_modified=False)

	for invoice in invoices:
		if frappe.db.get_value(INVOICE, invoice, "uae_reconciliation_status") == STATUS_IGNORED:
			frappe.db.set_value(INVOICE, invoice, "uae_reconciliation_status", "", update_modified=False)


def release_cancelled_invoice(doc, method=None) -> None:
	"""A cancelled Purchase Invoice is no longer what an e-invoice was matched to."""
	for log in frappe.get_all(LOG, filters={"link_name": doc.name}, pluck="name"):
		frappe.db.set_value(LOG, log, {"link_name": "", "match_status": ""}, update_modified=False)


def get_differences(received: dict, book: dict) -> str:
	"""What differs between a received e-invoice and a Purchase Invoice, for the report."""
	notes = []
	if not bill_numbers_match(received["number"], book["bill_no"]):
		notes.append(_("Number"))

	if received["date"] and book["date"] and getdate(received["date"]) != getdate(book["date"]):
		notes.append(_("Date"))

	if abs(abs(received["taxable"]) - abs(book["taxable"])) > 0.005:
		notes.append(_("Taxable amount"))

	if abs(abs(received["tax"]) - abs(book["tax"])) > 0.005:
		notes.append(_("VAT"))

	return ", ".join(notes)
