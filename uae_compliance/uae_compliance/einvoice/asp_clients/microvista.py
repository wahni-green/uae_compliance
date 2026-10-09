"""Adapter for the Microvista Peppol API.

Microvista takes the invoice's fields as JSON (not a PINT AE document), builds and checks the PINT AE
document itself with the official rules, sends it over the Peppol network and reports it to the FTA.
Behaviour was established against its sandbox:

- Authentication is a bearer token from `/api/auth/generate-authtoken` (valid for six minutes), sent
  together with the `x-apiSecret`, `x-secretKey` and `x-clientCode` headers on every call.
- `generate-invoice` answers HTTP 200 with `statusCode` 1 and the invoice id as `data` once the invoice
  is saved. A problem it can see at once comes back as `statusCode` 3 ("Validation failed") with
  messages; a number that was already used is one of them. Problems found by the PINT AE rules arrive
  later, as a failed status with the rule IDs and texts under `get-invoice-errors`.
- Status is by invoice id, passed as the `invoiceId` query parameter.
- Received invoices are listed per taxpayer and fetched by id as JSON.

Settings, in UAE E-Invoice Settings: Endpoint URL (the API base), Client ID (the API secret), Client
Secret (the secret key), and Extra Configuration with `client_code` and optionally `version` (default
`v1`), `inbound_days` (default 30) and `timeout` in seconds (default 60). The company's TIN is the
taxpayer."""

from datetime import date, datetime, timedelta

import frappe
import requests
from frappe import _
from frappe.utils import cint, flt

from uae_compliance.exceptions import (
	GatewayTimeoutError,
	ServiceProviderError,
	ServiceProviderLimitExceededError,
)
from uae_compliance.uae_compliance.constants.einvoice import (
	STATUS_CLEARED,
	STATUS_DELIVERED,
	STATUS_REJECTED,
	STATUS_SUBMITTED,
)
from uae_compliance.uae_compliance.constants.pint_ae import ENDPOINT_SCHEME, LEGAL_REGISTRATION_TYPES
from uae_compliance.uae_compliance.einvoice.asp_client import (
	ASPClient,
	InboundDocument,
	OutgoingDocument,
	StatusResult,
	SubmitResult,
)
from uae_compliance.uae_compliance.einvoice.exceptions import ProviderRejectedError
from uae_compliance.uae_compliance.einvoice.registry import register_provider

# The token lasts 360 seconds; it is renewed a minute early.
TOKEN_TTL = 300
PAGE_SIZE = 100
# Statuses of an invoice that failed, by code. The text also starts with "Failed".
FAILED_CODES = (3, 5)
DELIVERED_CODE = 200
DUPLICATE_MESSAGE = "already exists"


@register_provider
class MicrovistaASP(ASPClient):
	name = "Microvista"
	required_settings = ("endpoint_url", "client_id", "client_secret")

	# ------------------------------------------------------------------ connection

	@property
	def version(self) -> str:
		return self.config.extra.get("version", "v1")

	@property
	def timeout(self) -> int:
		return cint(self.config.extra.get("timeout")) or 60

	@property
	def taxpayer_tin(self) -> str:
		return frappe.db.get_value("Company", self.config.company, "uae_tin") or ""

	def _url(self, path: str) -> str:
		return f"{self.config.endpoint_url.rstrip('/')}{path}"

	def _token_key(self) -> str:
		return f"uae_compliance_microvista_token:{self.config.company}:{self.config.environment}"

	def _token(self, refresh: bool = False) -> str:
		if not refresh:
			cached = frappe.cache().get_value(self._token_key(), expires=True)
			if cached:
				return cached

		response = self._send(
			"/api/auth/generate-authtoken",
			json={
				"apiSecret": self.config.client_id,
				"secretKey": self.config.client_secret,
				"tin": self.taxpayer_tin,
			},
			authenticated=False,
		)
		body = self._json(response)
		token = (body.get("data") or {}).get("access_token") if isinstance(body.get("data"), dict) else None
		if not body.get("success") or not token:
			raise ServiceProviderError(
				_("Microvista refused the credentials: {0}").format(
					body.get("message") or response.status_code
				)
			)

		frappe.cache().set_value(self._token_key(), token, expires_in_sec=TOKEN_TTL)
		return token

	def _headers(self, token: str | None) -> dict:
		headers = {
			"x-apiSecret": self.config.client_id,
			"x-secretKey": self.config.client_secret,
			"x-clientCode": self.config.extra.get("client_code", ""),
			"Content-Type": "application/json",
		}
		if token:
			headers["Authorization"] = f"Bearer {token}"

		return headers

	def _send(self, path: str, *, authenticated: bool = True, token: str | None = None, **kwargs):
		"""One HTTP call. Timeouts, throttling and server errors are transient, so they raise errors the
		pipeline retries."""
		headers = self._headers(token) if authenticated else {"Content-Type": "application/json"}
		try:
			response = requests.post(self._url(path), headers=headers, timeout=self.timeout, **kwargs)
		except requests.Timeout as e:
			raise GatewayTimeoutError(_("Microvista did not answer in time")) from e
		except requests.ConnectionError as e:
			raise ServiceProviderError(_("Could not reach Microvista: {0}").format(str(e)[:200])) from e

		if response.status_code == 429:
			raise ServiceProviderLimitExceededError(_("Microvista is rate limiting this account"))
		if response.status_code >= 500:
			raise ServiceProviderError(_("Microvista failed with HTTP {0}").format(response.status_code))

		return response

	def _call(self, path: str, **kwargs) -> dict:
		"""An authenticated call that returns the parsed body. A rejected token is renewed once."""
		path = f"/api/einvoice/{self.version}/{path}"
		response = self._send(path, token=self._token(), **kwargs)
		if response.status_code == 401:
			response = self._send(path, token=self._token(refresh=True), **kwargs)

		if response.status_code in (401, 403):
			raise ServiceProviderError(
				_("Microvista refused the credentials (HTTP {0})").format(response.status_code)
			)

		return self._json(response)

	@staticmethod
	def _json(response) -> dict:
		try:
			body = response.json()
		except ValueError as e:
			raise ServiceProviderError(
				_("Microvista answered with something that is not JSON (HTTP {0})").format(
					response.status_code
				)
			) from e

		return body if isinstance(body, dict) else {"data": body}

	@staticmethod
	def _problems(body: dict) -> list[str]:
		"""The messages of a failed request, whichever of Microvista's shapes they come in."""
		data = body.get("data")
		messages = []
		if isinstance(data, list):
			for item in data:
				messages.append(item.get("message") if isinstance(item, dict) else str(item))
		elif isinstance(data, str):
			messages.append(data)

		return [m for m in messages if m] or [body.get("message") or "Rejected"]

	# ------------------------------------------------------------------ the interface

	def validate_credentials(self) -> None:
		self._token(refresh=True)

	def submit(self, document: OutgoingDocument, idempotency_key: str) -> SubmitResult:
		"""Send the invoice. Microvista identifies an invoice by its number and has no idempotency key,
		so a number that already exists is looked up instead of being treated as a failure: that is
		what a retry looks like when the first attempt reached Microvista but its answer did not
		reach us."""
		body = self._call("generate-invoice", json=to_payload(document.model))

		if body.get("status") == 400 or (not body.get("success") and body.get("statusCode") != 3):
			raise ProviderRejectedError("; ".join(self._problems(body)))

		if body.get("statusCode") == 3:
			problems = self._problems(body)
			if any(DUPLICATE_MESSAGE in problem.lower() for problem in problems):
				return self._find_existing(document)

			raise ProviderRejectedError("; ".join(problems))

		reference = body.get("data")
		if not isinstance(reference, str) or not reference:
			raise ServiceProviderError(_("Microvista did not return an invoice id"))

		return SubmitResult(
			provider_reference=reference,
			status=STATUS_SUBMITTED,
			detail=body.get("message") or "",
			raw_response=frappe.as_json(body),
		)

	def _find_existing(self, document: OutgoingDocument) -> SubmitResult:
		"""The invoice Microvista already holds under this number, found among the taxpayer's invoices
		of the day it was issued."""
		issued = document.model["issue_date"]
		start = 0
		while True:
			body = self._call(
				"get-invoice-details",
				json={
					"fromDate": f"{issued}T00:00:00.000Z",
					"toDate": f"{issued}T23:59:59.000Z",
					"pageSize": PAGE_SIZE,
					"pageStart": start,
					"tin": self.taxpayer_tin,
				},
			)
			rows = ((body.get("data") or {}).get("paginationData")) or []
			for row in rows:
				if row.get("invoiceNumber") == document.number:
					return SubmitResult(
						provider_reference=row["invoiceMasterId"],
						status=map_status(row.get("invoiceStatus"), row.get("invoiceStatusText"), None)[0],
						detail=_("Already held by Microvista"),
					)

			if len(rows) < PAGE_SIZE:
				break

			start += PAGE_SIZE

		raise ProviderRejectedError(
			_(
				"Microvista says invoice number {0} exists, but it is not among the taxpayer's invoices of {1}."
			).format(document.number, issued)
		)

	def get_status(self, provider_reference: str) -> StatusResult:
		body = self._call("get-invoice-status", params={"invoiceId": provider_reference}, json={})
		data = body.get("data")
		if not body.get("success") or not isinstance(data, dict):
			raise ServiceProviderError(
				_("Microvista could not give the status: {0}").format(body.get("message"))
			)

		status, detail = map_status(
			data.get("invoicestatuscode"),
			data.get("invoicestatus"),
			data.get("ftastatus"),
			data.get("buyerstatus"),
		)
		if status == STATUS_REJECTED:
			detail = "; ".join(self._errors(provider_reference)) or detail

		return StatusResult(status=status, detail=detail, raw_response=frappe.as_json(body))

	def _errors(self, provider_reference: str) -> list[str]:
		"""The PINT AE rules a failed invoice broke, as "rule id: text"."""
		body = self._call("get-invoice-errors", params={"invoiceId": provider_reference}, json={})
		return [
			f"{error.get('errorId')}: {error.get('errorText')}"
			for error in (body.get("data") or [])
			if isinstance(error, dict)
		]

	def fetch_inbound(self, known_references: set[str] | None = None) -> list[InboundDocument]:
		"""The invoices received in the last `inbound_days` days that are not logged yet, each fetched
		by id for its currency and number of lines."""
		known = known_references or set()
		today = date.today()
		start_date = today - timedelta(days=cint(self.config.extra.get("inbound_days")) or 30)
		documents = []
		start = 0
		while True:
			body = self._call(
				"get-purchase-invoice-details",
				json={
					"fromDate": f"{start_date.isoformat()}T00:00:00.000Z",
					"toDate": f"{today.isoformat()}T23:59:59.000Z",
					"pageSize": PAGE_SIZE,
					"pageStart": start,
					"tin": self.taxpayer_tin,
				},
			)
			rows = ((body.get("data") or {}).get("paginationData")) or []
			for row in rows:
				reference = row.get("invoiceMasterId")
				if not reference or reference in known:
					continue

				documents.append(
					InboundDocument(provider_reference=reference, model=self._inbound_model(row))
				)

			if len(rows) < PAGE_SIZE:
				return documents

			start += PAGE_SIZE

	def _inbound_model(self, row: dict) -> dict:
		"""A received invoice in the shape `inbound.parse_document` gives. The list carries the
		header; the invoice itself supplies the currency and the lines."""
		detail = (
			self._call(
				"get-purchase-invoice-details-by-id", params={"invoiceId": row["invoiceMasterId"]}, json={}
			).get("data")
			or {}
		)
		invoice = detail.get("Invoice") or detail.get("invoice") or {}
		lines = detail.get("Items") or detail.get("items") or []
		issued = row.get("invoiceDate") or ""

		return {
			"kind": "CreditNote" if row.get("invoiceType") in ("381", "81") else "Invoice",
			"type_code": row.get("invoiceType") or "",
			"number": row.get("invoiceNumber") or "",
			"uuid": row.get("uuid") or "",
			"issue_date": _iso_date(issued),
			"currency": invoice.get("invoiceCurrencyCode") or "AED",
			"seller_tin": row.get("sellerElectronicID") or "",
			"seller_trn": row.get("sellerTRN") or "",
			"seller_name": row.get("sellerName") or "",
			"buyer_tin": row.get("buyerElectronicID") or "",
			"buyer_trn": row.get("buyerTRN") or "",
			"tax_total": flt(row.get("taxAmount")),
			"payable": flt(row.get("totalAmount")),
			"lines": len(lines),
		}


# ---------------------------------------------------------------------- mapping


def _iso_date(value: str) -> str:
	"""Microvista lists dates as DD-MM-YYYY."""
	for pattern in ("%d-%m-%Y", "%Y-%m-%d"):
		try:
			return datetime.strptime(value[:10], pattern).date().isoformat()
		except ValueError:
			continue

	return ""


def map_status(
	code, text: str | None, fta_text: str | None, buyer_text: str | None = None
) -> tuple[str, str]:
	"""A Microvista status as one of ours, with the text to show.

	Code 200 is delivered. It counts as Cleared once the FTA corner has it too, and as Delivered while
	only the buyer's side does. Codes 3 and 5 (and anything that reads "Failed") are failures at the
	seller's own provider and at the FTA. Everything else is still on its way."""
	text = text or ""
	code = cint(code) if code is not None else None

	if code in FAILED_CODES or text.lower().startswith("failed"):
		return STATUS_REJECTED, text or _("Failed")

	if code == DELIVERED_CODE:
		if fta_text is None or fta_text.lower().startswith("delivered"):
			return STATUS_CLEARED, text
		return STATUS_DELIVERED, text

	return STATUS_SUBMITTED, text


def _build_payload(model: dict) -> dict:
	seller, buyer = model["seller"], model["buyer"]
	credit = model.get("credit_note") or {}
	totals = model["totals"]
	categories = {entry["code"]: entry for entry in model["breakdown"]}

	def taxable(code):
		return categories[code]["taxable"] if code in categories else 0.0

	def tax(code):
		return categories[code]["tax"] if code in categories else 0.0

	return {
		"invoice": {
			"invoiceNumber": model["number"],
			"invoiceIssueDate": model["issue_date"],
			"invoiceIssueTime": model["issue_time"][:8],
			"invoiceTypeCode": model["type_code"],
			"invoiceTransactionTypeCode": model["transaction_flags"],
			"invoiceCurrencyCode": model["currency"],
			"currencyExchangeRate": model["exchange_rate"] or 1.0,
			"taxAccountingCurrency": "AED",
			"vatPointDate": model.get("vat_point_date"),
			"creditNoteReasonCode": credit.get("reason_code"),
			"precedingInvoiceReference": credit.get("preceding_number"),
			"precedingInvoiceIssueDate": credit.get("preceding_date"),
			"invoiceNote": None,
		},
		"seller": {
			"name": seller["legal_name"],
			"supplierTradingName": seller["name"],
			"legalRegistrationIdentifier": seller["legal_id"],
			"legalRegistrationIdentifierType": LEGAL_REGISTRATION_TYPES.get(seller["legal_type"]),
			"authorityName": seller["authority"],
			"passportIssuingCountryCode": seller.get("passport_country"),
			"vatIdentifier": seller["trn"],
			"tin": seller["endpoint"],
			"electronicaddressScheme": ENDPOINT_SCHEME,
			"electronicAddress": seller["endpoint"],
			"addressLine1": seller["address"].get("street"),
			"city": seller["address"].get("city"),
			"countryCode": seller["address"].get("country") or "AE",
			"uaeStateCodes": seller["address"].get("subdivision"),
		},
		"buyer": {
			"buyerName": buyer["legal_name"],
			"tradingName": buyer["name"],
			"type": "BuyerOnly",
			"identifier": buyer["endpoint"],
			"buyerSchemeIdentifier": ENDPOINT_SCHEME,
			"vatIdentifier": buyer["trn"],
			"legalRegistrationIdentifier": buyer["legal_id"],
			"legalRegistrationIdentifierType": LEGAL_REGISTRATION_TYPES.get(buyer["legal_type"]),
			"authorityName": buyer["authority"],
			"passportIssuingCountryCode": buyer.get("passport_country"),
			"tin": buyer["endpoint"],
			"electronicAddress": buyer["endpoint"],
			"electronicAddressSchemeIdentifier": ENDPOINT_SCHEME,
			"addressLine1": buyer["address"].get("street"),
			"city": buyer["address"].get("city"),
			"countrySubdivision": buyer["address"].get("subdivision"),
			"uaeStateCodes": buyer["address"].get("subdivision"),
			"countryCode": buyer["address"].get("country") or "AE",
		},
		"invoiceDetail": {
			"sumOfInvoiceLineNetAmount": totals["line_total"],
			"invoiceTotalAmountWithoutTax": totals["tax_exclusive"],
			"invoiceTotalTaxAmount": totals["tax_total"],
			"invoiceTotalAmountWithTax": totals["tax_inclusive"],
			"roundingAmount": totals["rounding"],
			"amountDueForPayment": totals["payable"],
			"invoiceTotalTaxAmountInTaxAccountingCurrency": totals["tax_total_aed"],
			"taxableStandardRate": taxable("S"),
			"taxAmountStandardRate": tax("S"),
			"taxableZeroRated": taxable("Z"),
			"taxAmountZeroRated": tax("Z"),
			"taxableExempt": taxable("E"),
			"taxAmountExempt": tax("E"),
		},
		"delivery": {},
		"payment": {
			"paymentMeansTypeCode": model.get("payment_means_code"),
			"paymentDueDate": model.get("due_date"),
		},
		"items": [
			{
				"invoiceLineIdentifier": str(line["id"]),
				"itemType": line["item_type_code"],
				"itemClassificationSchemeIdentifier": "HS" if line["hs_code"] else None,
				"itemClassificationIdentifier": line["hs_code"],
				"serviceAccountingCode": line["sac_code"],
				"itemName": line["name"],
				"itemDescription": line["description"],
				"itemPriceBaseQuantity": 1.0,
				"itemGrossPrice": line["gross_price"],
				"itemPriceDiscount": line["discount"],
				"itemNetPrice": line["net_price"],
				"invoicedQuantity": line["quantity"],
				"invoicedQuantityUnitOfMeasureCode": line["unit_code"],
				"invoiceLineNetAmount": line["net_amount"],
				"invoicedItemTaxCategoryCode": line["category_code"],
				"invoicedItemTaxRate": line["rate"] if line["category_code"] != "E" else None,
				"invoiceLineAmountInAED": line["amount_aed"],
				"vatLineAmountInAED": line["vat_amount_aed"],
				"vatLineAmount": line["vat_amount"] if line["category_code"] != "E" else None,
				"taxExemptionReasonCode": line["exemption_reason_code"],
			}
			for line in model["lines"]
		],
		"additionalDocumentDetails": {"supportingDocuments": []},
	}


# Microvista refuses a request in which one of these fields is absent ("Field Is Missing"), even when
# it is empty, so they are always sent. Found with the sandbox; extend the list if it names more.
ALWAYS_SENT = {
	"buyer": ("emailID", "postCode", "buyerCode", "contactNo", "addressLine2", "passportIssuingCountryCode"),
}


def _clean(value, always: tuple[str, ...] = ()):
	"""Drop empty values, so the body carries only what the invoice has, except the fields the API
	insists on."""
	if isinstance(value, dict):
		return {k: _clean(v) for k, v in value.items() if v not in (None, "") or k in always}
	if isinstance(value, list):
		return [_clean(v) for v in value]

	return value


def to_payload(model: dict) -> dict:
	"""The `generate-invoice` body for an invoice model (see PintAEBuilder.build_all)."""
	payload = _build_payload(model)
	for section, fields in ALWAYS_SENT.items():
		for field in fields:
			payload[section].setdefault(field, "")

	return {name: _clean(value, ALWAYS_SENT.get(name, ())) for name, value in payload.items()}
