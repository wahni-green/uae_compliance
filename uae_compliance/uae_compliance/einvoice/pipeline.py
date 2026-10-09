"""Sending Sales Invoices as e-invoices.

On submission an in-scope invoice gets a UAE E-Invoice Log, its PINT AE XML is built and checked, and
it is sent to the company's provider in the background. The scheduler retries transient failures with
backoff and polls the provider until the invoice is Cleared (reported to the FTA) or Rejected."""

import json

import frappe
from frappe import _
from frappe.utils import add_to_date, add_years, cint, get_datetime, getdate, now_datetime

from uae_compliance.exceptions import ServiceProviderError
from uae_compliance.uae_compliance.constants.einvoice import (
	BACKOFF_MINUTES,
	DEFAULT_RETRY_LIMIT,
	DIRECTION_OUTBOUND,
	POLL_STATUSES,
	RETENTION_YEARS,
	SENT_STATUSES,
	STATUS_CLEARED,
	STATUS_FAILED,
	STATUS_GENERATED,
	STATUS_INVALID,
	STATUS_REJECTED,
	SUBMIT_PENDING_STATUSES,
)
from uae_compliance.uae_compliance.einvoice.asp_client import OutgoingDocument
from uae_compliance.uae_compliance.einvoice.exceptions import (
	EInvoiceError,
	EInvoiceNotSupportedError,
	ProviderRejectedError,
)
from uae_compliance.uae_compliance.einvoice.pint_ae_builder import build_document, build_xml
from uae_compliance.uae_compliance.einvoice.registry import get_client, get_company_setting
from uae_compliance.uae_compliance.einvoice.validators import validate_xml
from uae_compliance.uae_compliance.utils.company import is_uae_company

DOCTYPE = "Sales Invoice"
LOG = "UAE E-Invoice Log"


def get_setting_if_required(doc):
	"""The company's e-invoicing setting when this invoice has to be sent, else None. B2C sales, to
	an individual, are out of scope, as are invoices dated before the company's start date."""
	if not is_uae_company(doc.get("company")):
		return None

	row = get_company_setting(doc.company)
	if not row:
		return None

	if row.mandatory_from and getdate(doc.posting_date) < getdate(row.mandatory_from):
		return None

	if frappe.db.get_value("Customer", doc.customer, "customer_type") == "Individual":
		return None

	return row


# ---------------------------------------------------------------- document hooks


def validate_before_submit(doc, method=None):
	"""Stop an invoice that cannot be sent from being issued, so its problems are fixed while it is
	still a draft. An invoice that uses something the builder does not support yet is let through and
	logged as Invalid on submission instead, to be sent by other means."""
	if not get_setting_if_required(doc):
		return

	try:
		xml, _summary = build_xml(doc)
	except EInvoiceNotSupportedError:
		return

	errors = validate_xml(xml)
	if errors:
		frappe.throw("<br>".join(errors), exc=EInvoiceError, title=_("Invalid E-Invoice"))


def queue_einvoice(doc, method=None):
	"""On submission: log the invoice and send it in the background."""
	row = get_setting_if_required(doc)
	if not row:
		return

	log = create_log(doc, row)
	if log.status == STATUS_GENERATED:
		frappe.enqueue(
			"uae_compliance.uae_compliance.einvoice.pipeline.submit_log",
			log=log.name,
			queue="short",
			enqueue_after_commit=True,
		)
	elif log.status == STATUS_INVALID:
		frappe.msgprint(
			_("This invoice could not be turned into an e-invoice: {0}. See {1}.").format(
				log.errors, frappe.utils.get_link_to_form(LOG, log.name)
			),
			indicator="orange",
			alert=True,
		)


def guard_cancellation(doc, method=None):
	"""A sent e-invoice cannot be cancelled: a credit note corrects it. One that was never sent is
	closed, so that no queued job, scheduler run or retry sends it afterwards."""
	name = frappe.db.get_value(LOG, {"reference_doctype": DOCTYPE, "reference_name": doc.name})
	if not name:
		return

	# The lock is the one sending takes, so a send in progress finishes before this decides.
	frappe.db.get_value(LOG, name, "name", for_update=True)
	log = frappe.get_doc(LOG, name)
	if log.status in SENT_STATUSES:
		frappe.throw(
			_("This invoice has been sent as an e-invoice ({0}). Issue a credit note instead.").format(
				_(log.status)
			),
			title=_("E-Invoice Already Sent"),
		)

	if log.last_attempt_on and log.status in (STATUS_GENERATED, STATUS_FAILED):
		frappe.throw(
			_(
				"Sending this invoice was attempted and its outcome is not known: the provider may hold it. "
				"Retry it until it is settled, then issue a credit note if needed."
			),
			title=_("E-Invoice Status Unknown"),
		)

	if log.status != STATUS_INVALID or not log.errors:
		log.errors = _("The invoice was cancelled.")
		_set_status(log, STATUS_INVALID, _("Cancelled before it was sent"))
		log.next_attempt_on = None
		log.flags.ignore_permissions = True
		log.save()
		_mirror_status(log)


# ---------------------------------------------------------------- the log


def get_log(doc_name: str):
	name = frappe.db.get_value(LOG, {"reference_doctype": DOCTYPE, "reference_name": doc_name})
	return frappe.get_doc(LOG, name) if name else None


def create_log(doc, row):
	"""The log of an invoice, created on first use. Building and checking the XML decides whether it
	starts as Generated or Invalid."""
	log = get_log(doc.name)
	if not log:
		log = frappe.get_doc(
			{
				"doctype": LOG,
				"company": doc.company,
				"direction": DIRECTION_OUTBOUND,
				"reference_doctype": DOCTYPE,
				"reference_name": doc.name,
				"document_number": doc.name,
				"provider": row.provider,
				"environment": row.environment,
				"retain_until": add_years(getdate(doc.posting_date), RETENTION_YEARS),
			}
		)
		log.flags.ignore_permissions = True
		log.insert()

	prepare(log, doc)
	return log


def prepare(log, doc=None):
	"""Build and check the XML, leaving the log Generated when it passes and Invalid when it does not."""
	doc = doc or frappe.get_doc(DOCTYPE, log.reference_name)
	before = doc.get("uae_einvoice_uuid")

	try:
		xml, _summary, model = build_document(doc)
		errors = validate_xml(xml)
	except EInvoiceError as e:
		xml, model, errors = b"", {}, [str(e)]

	if doc.get("uae_einvoice_uuid") != before:
		frappe.db.set_value(
			DOCTYPE, doc.name, "uae_einvoice_uuid", doc.uae_einvoice_uuid, update_modified=False
		)

	log.uuid = doc.get("uae_einvoice_uuid")
	log.xml = xml.decode() if xml else ""
	log.payload = frappe.as_json(model) if model else ""
	log.errors = "\n".join(errors)
	# A new send gets a new key only when the last one definitely did not reach the provider. After a
	# timeout it might have, so the same key is kept and the provider can recognise the repeat.
	uncertain = bool(log.last_attempt_on) and log.status in (STATUS_GENERATED, STATUS_FAILED)
	if not log.idempotency_key or not uncertain:
		log.idempotency_key = f"{log.name}-{frappe.generate_hash(length=8)}"

	log.attempts = 0
	# A due date from the start, so the scheduler sends it if the queued job is lost.
	log.next_attempt_on = None if errors else now_datetime()
	_set_status(log, STATUS_INVALID if errors else STATUS_GENERATED, "")
	log.flags.ignore_permissions = True
	log.save()
	_mirror_status(log)


def _set_status(log, status: str, detail: str | None = None):
	log.status = status
	if detail is not None:
		log.status_detail = detail


def _mirror_status(log):
	"""Show the status on the invoice."""
	if log.reference_doctype == DOCTYPE:
		frappe.db.set_value(
			DOCTYPE,
			log.reference_name,
			{"uae_einvoice_status": log.status, "uae_einvoice_log": log.name},
			update_modified=False,
		)


# ---------------------------------------------------------------- sending and polling


def _retry_limit() -> int:
	return cint(frappe.db.get_single_value("UAE E-Invoice Settings", "retry_limit")) or DEFAULT_RETRY_LIMIT


def submit_log(log: str) -> None:
	"""Send a Generated document to the provider. Transient failures are retried later with backoff,
	and a refusal by the provider is final."""
	name = log
	# Locking the row keeps a manual retry and the scheduler from sending the same document twice.
	frappe.db.get_value(LOG, name, "name", for_update=True)
	log = frappe.get_doc(LOG, name)
	if log.status not in SUBMIT_PENDING_STATUSES:
		return

	if frappe.db.get_value(log.reference_doctype, log.reference_name, "docstatus") != 1:
		log.errors = _("The invoice is not submitted.")
		_set_status(log, STATUS_INVALID, _("The invoice is not submitted"))
		log.next_attempt_on = None
		log.flags.ignore_permissions = True
		log.save()
		_mirror_status(log)
		return

	log.attempts = cint(log.attempts) + 1
	log.last_attempt_on = now_datetime()

	try:
		result = _client_for(log).submit(
			OutgoingDocument(
				number=log.document_number,
				uuid=log.uuid,
				xml=log.xml.encode(),
				model=json.loads(log.payload) if log.payload else {},
				metadata={"company": log.company},
			),
			log.idempotency_key,
		)
	except ProviderRejectedError as e:
		log.errors = str(e)
		_set_status(log, STATUS_REJECTED, _("Rejected by the provider"))
	except Exception as e:
		_handle_transient_failure(log, e)
	else:
		log.provider_reference = result.provider_reference
		log.response = result.raw_response
		log.errors = ""
		log.next_attempt_on = None
		_apply_result(log, result.status, result.detail)

	log.flags.ignore_permissions = True
	log.save()
	_mirror_status(log)


def _client_for(log):
	"""The client for a log, refusing to use settings that are not the ones it was created under: the
	reference of a document is only meaningful to the provider and environment that issued it."""
	row = get_company_setting(log.company)
	if row and (row.provider != log.provider or row.environment != log.environment):
		raise ServiceProviderError(
			_("The provider settings of {0} changed since {1} was created ({2}, {3}).").format(
				log.company, log.name, log.provider, log.environment
			)
		)

	return get_client(log.company)


def _apply_result(log, status: str, detail: str | None) -> None:
	"""Set a status from the provider, recording the clearance date and retention when it is Cleared."""
	_set_status(log, status, detail)
	if status == STATUS_CLEARED:
		log.cleared_on = log.cleared_on or now_datetime()
		log.retain_until = max(
			getdate(log.retain_until or log.cleared_on), add_years(getdate(log.cleared_on), RETENTION_YEARS)
		)


def _handle_transient_failure(log, error: Exception) -> None:
	if not isinstance(error, ServiceProviderError):
		frappe.log_error(title=f"E-invoice submission failed: {log.name}")

	log.errors = str(error)
	if cint(log.attempts) >= _retry_limit():
		_set_status(log, STATUS_FAILED, _("Gave up after {0} attempts").format(log.attempts))
		log.next_attempt_on = None
		return

	delay = BACKOFF_MINUTES * 2 ** (cint(log.attempts) - 1)
	log.next_attempt_on = add_to_date(now_datetime(), minutes=delay)
	_set_status(log, STATUS_GENERATED, _("Will retry in {0} minutes").format(delay))


def poll_log(log: str) -> None:
	"""Ask the provider where a sent document stands."""
	name = log
	frappe.db.get_value(LOG, name, "name", for_update=True)
	log = frappe.get_doc(LOG, name)
	if log.status not in POLL_STATUSES or not log.provider_reference:
		return

	try:
		result = _client_for(log).get_status(log.provider_reference)
	except Exception:
		# A failed check is not a failed invoice: try again at the next poll, after the others.
		frappe.log_error(title=f"E-invoice status check failed: {log.name}")
		frappe.db.set_value(LOG, name, "last_attempt_on", now_datetime())
		return

	log.response = result.raw_response or log.response
	_apply_result(log, result.status, result.detail)

	log.flags.ignore_permissions = True
	log.save()
	_mirror_status(log)


def retry_log(log: str) -> None:
	"""Rebuild the XML from the invoice as it is now and send it again."""
	frappe.db.get_value(LOG, log, "name", for_update=True)
	doc_log = frappe.get_doc(LOG, log)
	if doc_log.status in SENT_STATUSES:
		frappe.throw(_("This e-invoice has already been sent."))

	if frappe.db.get_value(doc_log.reference_doctype, doc_log.reference_name, "docstatus") != 1:
		frappe.throw(_("The invoice is not submitted, so it cannot be sent."))

	prepare(doc_log)
	doc_log.reload()
	if doc_log.status == STATUS_GENERATED:
		submit_log(doc_log.name)
	else:
		frappe.throw(doc_log.errors, exc=EInvoiceError, title=_("Invalid E-Invoice"))


# ---------------------------------------------------------------- scheduler


def process_pending() -> None:
	"""Scheduler job: send what is waiting and is due, then check what has been sent."""
	now = get_datetime(now_datetime())
	due = frappe.get_all(
		LOG,
		filters={
			"direction": DIRECTION_OUTBOUND,
			"status": ["in", SUBMIT_PENDING_STATUSES],
			"next_attempt_on": ["<=", now],
		},
		pluck="name",
		order_by="next_attempt_on asc",
		limit=50,
	)
	for name in due:
		_run(submit_log, name)

	for name in frappe.get_all(
		LOG,
		filters={"direction": DIRECTION_OUTBOUND, "status": ["in", POLL_STATUSES]},
		pluck="name",
		# Every check or failed check updates the log, so the one checked longest ago comes first.
		order_by="modified asc",
		limit=50,
	):
		_run(poll_log, name)


def _run(function, name: str) -> None:
	"""One document's failure must not stop the others."""
	try:
		function(name)
		frappe.db.commit()  # nosemgrep
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"E-invoice job failed: {name}")
