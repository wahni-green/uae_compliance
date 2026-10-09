"""FTA Audit File (FAF) generator.

The layout follows Appendix 5 of the FTA "Requirements Document for Tax Accounting Software"
(October 2017): comma separated values with four tables (company information, supplier listing,
customer listing, general ledger). That document is the only layout specification found, and it
may have been superseded, so treat the output as based on the 2017 specification. See
docs/UAE_VERIFICATION.md.
"""

import csv
import io

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, now_datetime

import uae_compliance
from uae_compliance.uae_compliance.utils.vat_return import get_invoice_rows

FAF_VERSION = "FAFv1.0.0"
EMPTY_CURRENCY = "XXX"

# Tax codes from Appendix 3 of the same document.
SALES_TAX_CODES = {"Standard Rated": "SR", "Zero Rated": "ZR", "Exempt": "EX"}
PURCHASE_TAX_CODES = {"Standard Rated": "SR", "Zero Rated": "ZR", "Exempt": "EX"}
REVERSE_CHARGE_CODE = "RC"


def generate_faf(company: str, from_date, to_date) -> str:
	"""The FAF for a company and period as CSV text: each table is a header row, its data rows and,
	for the three listings, a totals row, separated by a blank line."""
	# The export reads invoices and ledger entries through queries that bypass per-document
	# permissions, so access to each is checked up front. Reading the return is not enough.
	frappe.has_permission("Company", "read", doc=company, throw=True)
	for doctype in ("Sales Invoice", "Purchase Invoice", "GL Entry"):
		frappe.has_permission(doctype, "read", throw=True)

	sections = [
		_company_information(company, from_date, to_date),
		_supplier_listing(company, from_date, to_date),
		_customer_listing(company, from_date, to_date),
		_general_ledger(company, from_date, to_date),
	]

	out = io.StringIO()
	writer = csv.writer(out, lineterminator="\n")
	for index, (headers, rows, totals) in enumerate(sections):
		if index:
			writer.writerow([])

		writer.writerow(headers)
		writer.writerows(rows)
		if totals:
			writer.writerow(totals["headers"])
			writer.writerow(totals["values"])

	return out.getvalue()


def _text(value, length: int | None = None) -> str:
	"""Fields are comma separated, so a comma inside a value would be misread."""
	value = ("" if value is None else str(value)).replace(",", " ").replace("\n", " ").replace("\r", " ")
	return value[:length] if length else value


def _date(value) -> str:
	return formatdate(value, "dd-mm-yyyy") if value else "31-12-9999"


def _money(value) -> str:
	return f"{flt(value, 2):.2f}"


def _company_information(company: str, from_date, to_date):
	values = frappe.db.get_value("Company", company, ["uae_company_name_in_arabic", "uae_trn"], as_dict=True)
	app_version = getattr(uae_compliance, "__version__", "")
	erpnext_version = frappe.get_attr("erpnext.__version__")
	headers = [
		"TaxablePersonNameEn",
		"TaxablePersonNameAr",
		"TRN",
		"TaxAgencyName",
		"TAN",
		"TaxAgentName",
		"TAAN",
		"PeriodStart",
		"PeriodEnd",
		"FAFCreationDate",
		"ProductVersion",
		"FAFVersion",
	]
	row = [
		_text(company, 100),
		_text(values.uae_company_name_in_arabic, 100),
		_text(values.uae_trn, 15),
		"",
		"",
		"",
		"",
		_date(from_date),
		_date(to_date),
		_date(now_datetime().date()),
		_text(f"UAE Compliance {app_version} on ERPNext {erpnext_version}", 100),
		FAF_VERSION,
	]
	return headers, [row], None


def _party_details(doctype: str, names: set[str]) -> dict:
	"""Name, TRN and billing country for each party."""
	if not names:
		return {}

	name_field = "customer_name" if doctype == "Customer" else "supplier_name"
	parties = {
		party.name: party
		for party in frappe.get_all(
			doctype, filters={"name": ["in", list(names)]}, fields=["name", name_field, "uae_trn"]
		)
	}
	countries = dict(
		frappe.db.sql(
			"""
			SELECT dl.link_name, MIN(a.country)
			FROM `tabAddress` a
			JOIN `tabDynamic Link` dl ON dl.parent = a.name AND dl.parenttype = 'Address'
			WHERE dl.link_doctype = %(doctype)s AND dl.link_name IN %(names)s
			GROUP BY dl.link_name
			""",
			{"doctype": doctype, "names": tuple(names)},
		)
	)
	return {
		name: {
			"name": party.get(name_field) or name,
			"trn": party.uae_trn,
			"country": countries.get(name) or "",
		}
		for name, party in parties.items()
	}


def _invoice_headers(doctype: str, company: str, from_date, to_date) -> dict:
	party_field = "customer" if doctype == "Sales Invoice" else "supplier"
	extra = ["shipping_address_name"] if doctype == "Sales Invoice" else ["uae_permit_no"]
	return {
		invoice.name: invoice
		for invoice in frappe.get_all(
			doctype,
			filters={
				"company": company,
				"posting_date": ["between", [from_date, to_date]],
				"docstatus": 1,
			},
			fields=[
				"name",
				"posting_date",
				"currency",
				"conversion_rate",
				party_field,
				*extra,
			],
		)
	}


def _supplier_listing(company: str, from_date, to_date):
	rows = get_invoice_rows("Purchase Invoice", company, from_date, to_date)
	invoices = _invoice_headers("Purchase Invoice", company, from_date, to_date)
	parties = _party_details("Supplier", {invoice.supplier for invoice in invoices.values()})
	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	line_numbers = _line_numbers("Purchase Invoice Item", invoices)

	headers = [
		"SupplierName",
		"SupplierCountry",
		"SupplierTRN",
		"InvoiceDate",
		"InvoiceNo",
		"PermitNo",
		"TransactionID",
		"LineNo",
		"ProductDescription",
		"PurchaseValueAED",
		"VATValueAED",
		"TaxCode",
		"FCYCode",
		"PurchaseFCY",
		"VATFCY",
	]
	data, total_value, total_vat = [], 0.0, 0.0
	for row in sorted(rows, key=lambda r: (invoices[r.invoice].posting_date, r.invoice)):
		invoice = invoices[row.invoice]
		party = parties.get(invoice.supplier, {"name": invoice.supplier, "trn": "", "country": ""})
		foreign = invoice.currency != company_currency
		rate = flt(invoice.conversion_rate) or 1
		vat = flt(row.input_vat_amount) or flt(row.output_vat_amount)
		code = REVERSE_CHARGE_CODE if row.uae_is_reverse_charge else PURCHASE_TAX_CODES[row.category]

		total_value += flt(row.base_net_amount)
		total_vat += vat
		data.append(
			[
				_text(party["name"], 100),
				_text(party["country"], 50),
				_text(party["trn"], 15),
				_date(invoice.posting_date),
				_text(row.invoice, 50),
				_text(invoice.uae_permit_no, 20),
				_text(row.invoice, 20),
				line_numbers.get(row.name, 0),
				_text(frappe.db.get_value("Purchase Invoice Item", row.name, "item_name"), 250),
				_money(row.base_net_amount),
				_money(vat),
				code,
				invoice.currency if foreign else EMPTY_CURRENCY,
				_money(flt(row.base_net_amount) / rate) if foreign else "0.00",
				_money(vat / rate) if foreign else "0.00",
			]
		)

	totals = {
		"headers": ["PurchaseTotalAED", "VATTotalAED", "TransactionCountTotal"],
		"values": [_money(total_value), _money(total_vat), len(data)],
	}
	return headers, data, totals


def _customer_listing(company: str, from_date, to_date):
	rows = get_invoice_rows("Sales Invoice", company, from_date, to_date)
	invoices = _invoice_headers("Sales Invoice", company, from_date, to_date)
	parties = _party_details("Customer", {invoice.customer for invoice in invoices.values()})
	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	line_numbers = _line_numbers("Sales Invoice Item", invoices)

	headers = [
		"CustomerName",
		"CustomerCountry",
		"CustomerTRN",
		"InvoiceDate",
		"InvoiceNo",
		"TransactionID",
		"LineNo",
		"ProductDescription",
		"SupplyValueAED",
		"VATValueAED",
		"TaxCode",
		"Country",
		"FCYCode",
		"SupplyFCY",
		"VATFCY",
	]
	data, total_value, total_vat = [], 0.0, 0.0
	for row in sorted(rows, key=lambda r: (invoices[r.invoice].posting_date, r.invoice)):
		invoice = invoices[row.invoice]
		party = parties.get(invoice.customer, {"name": invoice.customer, "trn": "", "country": ""})
		foreign = invoice.currency != company_currency
		rate = flt(invoice.conversion_rate) or 1
		vat = flt(row.output_vat_amount)

		destination = ""
		if row.uae_is_export and invoice.shipping_address_name:
			destination = frappe.db.get_value("Address", invoice.shipping_address_name, "country") or ""

		total_value += flt(row.base_net_amount)
		total_vat += vat
		data.append(
			[
				_text(party["name"], 100),
				_text(party["country"], 50),
				_text(party["trn"], 15),
				_date(invoice.posting_date),
				_text(row.invoice, 50),
				_text(row.invoice, 20),
				line_numbers.get(row.name, 0),
				_text(frappe.db.get_value("Sales Invoice Item", row.name, "item_name"), 250),
				_money(row.base_net_amount),
				_money(vat),
				SALES_TAX_CODES[row.category],
				_text(destination, 50),
				invoice.currency if foreign else EMPTY_CURRENCY,
				_money(flt(row.base_net_amount) / rate) if foreign else "0.00",
				_money(vat / rate) if foreign else "0.00",
			]
		)

	totals = {
		"headers": ["SupplyTotalAED", "VATTotalAED", "TransactionCountTotal"],
		"values": [_money(total_value), _money(total_vat), len(data)],
	}
	return headers, data, totals


def _line_numbers(child_doctype: str, invoices: dict) -> dict:
	if not invoices:
		return {}

	return dict(
		frappe.get_all(
			child_doctype,
			filters={"parent": ["in", list(invoices)]},
			fields=["name", "idx"],
			as_list=True,
		)
	)


def _account_ids(accounts: set[str]) -> dict[str, str]:
	"""The 20 character AccountID of each account: its account number if it has one, else its
	name. Two accounts that would end up with the same ID are refused rather than merged, because an
	auditor reading the file could not tell them apart."""
	numbers = dict(
		frappe.get_all(
			"Account",
			filters={"name": ["in", list(accounts)]},
			fields=["name", "account_number"],
			as_list=True,
		)
	)
	ids = {account: _text(numbers.get(account) or account, 20) for account in accounts}

	by_id: dict[str, list[str]] = {}
	for account, account_id in ids.items():
		by_id.setdefault(account_id, []).append(account)

	clashes = {account_id: names for account_id, names in by_id.items() if len(names) > 1}
	if clashes:
		account_id, names = next(iter(clashes.items()))
		frappe.throw(
			_(
				"The FAF limits an account ID to 20 characters, and these accounts would share the ID {0}: {1}. Give them account numbers."
			).format(frappe.bold(account_id), ", ".join(sorted(names))),
			title=_("Account IDs Clash"),
		)

	return ids


def _general_ledger(company: str, from_date, to_date):
	entries = frappe.get_all(
		"GL Entry",
		filters={
			"company": company,
			"posting_date": ["between", [from_date, to_date]],
			"is_cancelled": 0,
		},
		fields=[
			"posting_date",
			"account",
			"remarks",
			"party",
			"voucher_no",
			"voucher_type",
			"against_voucher",
			"debit",
			"credit",
		],
		order_by="posting_date, account, voucher_no, creation",
	)
	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	account_ids = _account_ids({entry.account for entry in entries})

	headers = [
		"TransactionDate",
		"AccountID",
		"AccountName",
		"TransactionDescription",
		"Name",
		"TransactionID",
		"SourceDocumentID",
		"SourceType",
		"Debit",
		"Credit",
		"Balance",
	]
	data, balances = [], {}
	total_debit = total_credit = 0.0
	for entry in entries:
		balances[entry.account] = balances.get(entry.account, 0) + flt(entry.debit) - flt(entry.credit)
		total_debit += flt(entry.debit)
		total_credit += flt(entry.credit)
		data.append(
			[
				_date(entry.posting_date),
				account_ids[entry.account],
				_text(entry.account, 100),
				_text(entry.remarks, 250),
				_text(entry.party, 100),
				_text(entry.voucher_no, 50),
				_text(entry.against_voucher or entry.voucher_no, 50),
				_text(entry.voucher_type, 20),
				_money(entry.debit),
				_money(entry.credit),
				_money(balances[entry.account]),
			]
		)

	totals = {
		"headers": ["TotalDebit", "TotalCredit", "TransactionCountTotal", "GLTCurrency"],
		"values": [_money(total_debit), _money(total_credit), len(data), company_currency],
	}
	return headers, data, totals
