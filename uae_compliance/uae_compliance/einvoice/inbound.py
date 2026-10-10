"""Receiving e-invoices: reading a PINT AE document sent to a company into its UAE E-Invoice Log."""

import frappe
from frappe import _
from frappe.utils import add_years, flt, getdate
from lxml import etree

from uae_compliance.uae_compliance.constants.einvoice import (
	DIRECTION_INBOUND,
	RETENTION_YEARS,
	STATUS_DELIVERED,
	STATUS_INVALID,
)
from uae_compliance.uae_compliance.einvoice.pint_ae_builder import NAMESPACES, ROOTS
from uae_compliance.uae_compliance.einvoice.registry import get_client, get_company_setting

LOG = "UAE E-Invoice Log"
_NS = {"cac": NAMESPACES["cac"], "cbc": NAMESPACES["cbc"]}


def _text(node, path: str) -> str:
	found = node.xpath(path, namespaces=_NS)
	return (found[0].text or "").strip() if found else ""


def parse_document(xml: bytes) -> dict:
	"""The header of a received PINT AE invoice or credit note. Raises ValueError if it is not one."""
	try:
		root = etree.fromstring(xml)
	except etree.XMLSyntaxError as e:
		raise ValueError(str(e)) from e

	kinds = {
		f"{{{ROOTS['Invoice']}}}Invoice": "Invoice",
		f"{{{ROOTS['CreditNote']}}}CreditNote": "CreditNote",
	}
	kind = kinds.get(root.tag)
	if not kind:
		raise ValueError(_("The document is neither an invoice nor a credit note."))

	seller = "cac:AccountingSupplierParty/cac:Party"
	buyer = "cac:AccountingCustomerParty/cac:Party"
	type_tag = "InvoiceTypeCode" if kind == "Invoice" else "CreditNoteTypeCode"
	line_tag = "InvoiceLine" if kind == "Invoice" else "CreditNoteLine"
	return {
		"kind": kind,
		"type_code": _text(root, f"cbc:{type_tag}"),
		"number": _text(root, "cbc:ID"),
		"uuid": _text(root, "cbc:UUID"),
		"issue_date": _text(root, "cbc:IssueDate"),
		"currency": _text(root, "cbc:DocumentCurrencyCode"),
		"seller_tin": _text(root, f"{seller}/cbc:EndpointID"),
		"seller_trn": _text(root, f"{seller}/cac:PartyTaxScheme/cbc:CompanyID"),
		"seller_name": _text(root, f"{seller}/cac:PartyLegalEntity/cbc:RegistrationName"),
		"buyer_tin": _text(root, f"{buyer}/cbc:EndpointID"),
		"buyer_trn": _text(root, f"{buyer}/cac:PartyTaxScheme/cbc:CompanyID"),
		"tax_total": flt(_text(root, "cac:TaxTotal/cbc:TaxAmount")),
		"payable": flt(_text(root, "cac:LegalMonetaryTotal/cbc:PayableAmount")),
		"lines": len(root.xpath(f"cac:{line_tag}", namespaces=_NS)),
	}


REQUIRED_KEYS = (
	"kind",
	"number",
	"uuid",
	"issue_date",
	"currency",
	"seller_name",
	"seller_tin",
	"seller_trn",
	"buyer_tin",
	"buyer_trn",
	"payable",
)


def receive(company: str) -> int:
	"""Fetch the documents the provider holds for a company and log the new ones. Returns how many
	were new. A document already logged under the same provider reference is skipped; references are
	only compared within the provider and environment in use, as another one may reuse them."""
	row = get_company_setting(company)
	if not row:
		return 0

	known = set(
		frappe.get_all(
			LOG,
			filters={
				"direction": DIRECTION_INBOUND,
				"company": company,
				"provider": row.provider,
				"environment": row.environment,
			},
			pluck="provider_reference",
		)
	)
	received = 0
	for document in get_client(company).fetch_inbound(known):
		if document.provider_reference in known:
			continue

		_log_document(company, document)
		known.add(document.provider_reference)
		received += 1

	return received


def _read_details(document) -> dict:
	"""The header of a received document, from its model or its XML. Raises ValueError when it cannot
	be read, so that one bad document is logged as Invalid instead of stopping the run."""
	if not document.model:
		return parse_document(document.xml or b"")

	missing = [key for key in REQUIRED_KEYS if key not in document.model]
	if missing:
		raise ValueError(_("The document is missing: {0}.").format(", ".join(missing)))

	return document.model


def _log_document(company: str, document) -> None:
	row = get_company_setting(company)
	log = frappe.get_doc(
		{
			"doctype": LOG,
			"company": company,
			"direction": DIRECTION_INBOUND,
			"provider": row.provider,
			"environment": row.environment,
			"provider_reference": document.provider_reference,
			"xml": document.xml.decode(errors="replace") if document.xml else "",
			"payload": frappe.as_json(document.model) if document.model else "",
			# The retention clock starts at receipt, and at the invoice date once that is known.
			"retain_until": add_years(getdate(), RETENTION_YEARS),
		}
	)

	problems = []
	try:
		details = _read_details(document)
		issued = _issue_date(details["issue_date"])
	except ValueError as e:
		details, issued = {}, None
		problems.append(str(e))

	if details:
		log.reference_doctype = None
		log.document_number = details["number"]
		log.uuid = details["uuid"]
		log.document_type = _("Credit Note") if details["kind"] == "CreditNote" else _("Invoice")
		log.document_date = issued
		log.party_name = details["seller_name"]
		log.party_tin = details["seller_tin"]
		log.currency = details["currency"]
		log.total_amount = details["payable"]
		log.supplier = _find_supplier(details)
		problems += _check_addressee(company, details)
		if issued:
			log.retain_until = max(log.retain_until, add_years(issued, RETENTION_YEARS))
		else:
			problems.append(_("The document has no valid issue date."))

	log.errors = "\n".join(problems)
	log.status = STATUS_INVALID if problems else STATUS_DELIVERED
	log.status_detail = _("Received from the provider")
	log.flags.ignore_permissions = True
	log.insert()


def _issue_date(value):
	"""The issue date, or None when there is none. Raises ValueError when it is not a date."""
	if not value:
		return None

	try:
		return getdate(value)
	except Exception as e:
		raise ValueError(_("The issue date {0} is not a valid date.").format(value)) from e


def _find_supplier(details: dict) -> str | None:
	"""The supplier master matching the sender, by TIN and then by TRN."""
	for field, value in (("uae_tin", details["seller_tin"]), ("uae_trn", details["seller_trn"])):
		if value:
			name = frappe.db.get_value("Supplier", {field: value})
			if name:
				return name

	return None


def _check_addressee(company: str, details: dict) -> list[str]:
	"""A document delivered to a company should be addressed to it."""
	tin, trn = frappe.db.get_value("Company", company, ["uae_tin", "uae_trn"])
	if details["buyer_tin"] and tin and details["buyer_tin"] != tin:
		return [_("The document is addressed to {0}, not to {1}.").format(details["buyer_tin"], tin)]

	if details["buyer_trn"] and trn and details["buyer_trn"] != trn:
		return [_("The document is addressed to TRN {0}, not to {1}.").format(details["buyer_trn"], trn)]

	return []
