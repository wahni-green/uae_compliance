"""Sending Sales Invoices as e-invoices.

On submission an in-scope invoice gets a UAE E-Invoice Log, its PINT AE XML is built and checked, and
it is sent to the company's provider in the background. The scheduler retries transient failures with
backoff and polls the provider until the invoice is Cleared (reported to the FTA) or Rejected."""

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
from uae_compliance.uae_compliance.einvoice.exceptions import (
	EInvoiceError,
	EInvoiceNotSupportedError,
	ProviderRejectedError,
)
from uae_compliance.uae_compliance.einvoice.pint_ae_builder import build_xml
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
	"""A sent e-invoice cannot be cancelled: a credit note corrects it."""
	status = frappe.db.get_value(LOG, {"reference_doctype": DOCTYPE, "reference_name": doc.name}, "status")
	if status in SENT_STATUSES:
		frappe.throw(
			_("This invoice has been sent as an e-invoice ({0}). Issue a credit note instead.").format(
				_(status)
			),
			title=_("E-Invoice Already Sent"),
		)


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
		xml, _summary = build_xml(doc)
		errors = validate_xml(xml)
	except EInvoiceError as e:
		xml, errors = b"", [str(e)]

	if doc.get("uae_einvoice_uuid") != before:
		frappe.db.set_value(
			DOCTYPE, doc.name, "uae_einvoice_uuid", doc.uae_einvoice_uuid, update_modified=False
		)

	log.uuid = doc.get("uae_einvoice_uuid")
	log.xml = xml.decode() if xml else ""
	log.errors = "\n".join(errors)
	log.idempotency_key = f"{log.name}-{frappe.generate_hash(length=8)}"
	log.attempts = 0
	log.next_attempt_on = None
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

	log.attempts = cint(log.attempts) + 1
	log.last_attempt_on = now_datetime()

	try:
		client = get_client(log.company)
		result = client.submit(
			log.xml.encode(),
			log.idempotency_key,
			{"number": log.document_number, "uuid": log.uuid, "company": log.company},
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
		_set_status(log, result.status, result.detail)

	log.flags.ignore_permissions = True
	log.save()
	_mirror_status(log)


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
		result = get_client(log.company).get_status(log.provider_reference)
	except Exception:
		# A failed check is not a failed invoice: try again at the next poll.
		frappe.log_error(title=f"E-invoice status check failed: {log.name}")
		return

	log.response = result.raw_response or log.response
	_set_status(log, result.status, result.detail)
	if result.status == STATUS_CLEARED:
		log.cleared_on = now_datetime()
		log.retain_until = max(
			getdate(log.retain_until or log.cleared_on), add_years(getdate(log.cleared_on), RETENTION_YEARS)
		)

	log.flags.ignore_permissions = True
	log.save()
	_mirror_status(log)


def retry_log(log: str) -> None:
	"""Rebuild the XML from the invoice as it is now and send it again."""
	doc_log = frappe.get_doc(LOG, log)
	if doc_log.status in SENT_STATUSES:
		frappe.throw(_("This e-invoice has already been sent."))

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
		limit=50,
	)
	for name in due:
		_run(submit_log, name)

	for name in frappe.get_all(
		LOG,
		filters={"direction": DIRECTION_OUTBOUND, "status": ["in", POLL_STATUSES]},
		pluck="name",
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
