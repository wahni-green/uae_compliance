"""Adapter for the ClearTax e-invoicing API (MEA region).

ClearTax takes the invoice as a PINT AE JSON document (Base64 encoded, camelCase), not as XML, and
fills in the fixed parts itself. Behaviour was established against its sandbox:

- Authentication is an access token for the account's client secret (`/integration/v1/authz/token`).
  The token does not expire, and creating a new one revokes the previous one, so it is shared through
  the cache and renewed, under a lock, only after the API refuses it.
- Every call carries the company's TIN (`x-clear-tin`) and the country. `x-clear-trn` and
  `x-clear-branch` are sent only when configured: a wrong TRN is refused with a bare 403.
- `documents/send` answers HTTP 200 with a document ID once the document is accepted for processing.
  What a PINT AE rule or the Peppol network finds wrong comes later, in the status, as a failed
  document with the rule IDs (`CLEARTAX`) or the network's error (`PEPPOL`).
- A document number can be sent once. Sending it again, even after a failure, answers `300118` ("in
  progress") with no document ID, so that answer is the look up of the document ClearTax already
  holds, not an error. The lookup is by the issue date, which is what the listing filters on.
- A payload ClearTax cannot read is answered with HTTP 400 or 406.

Settings, in UAE E-Invoice Settings: Endpoint URL (the API base, for example
`https://api-sandbox.mea.cleartax.com`) and Client Secret; Extra Configuration may hold `trn`,
`branch`, `inbound_days` (default 30) and `timeout` in seconds (default 60). The company's TIN is the
taxpayer."""

import base64
import hashlib
import json
from datetime import date, timedelta

import frappe
import requests
from frappe import _
from frappe.utils import cint, flt
from frappe.utils.synchronization import filelock

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

SCHEMA = "CLEAR_UNIFIED_SCHEMA"
CUSTOMIZATION_ID = "urn:peppol:pint:billing-1@ae-1"
PROFILE_ID = "urn:peppol:bis:billing"
# The listing refuses a range of more than seven days (its end date minus its start date).
LIST_SPAN_DAYS = 6
PAGE_SIZE = 100
# "Submission Request for same uniqueId ... is in progress": the number was sent before.
ALREADY_SENT = "300118"
REPORTED = "ACCEPTED"
NO_RATE_CATEGORIES = ("E", "O")


@register_provider
class ClearTaxASP(ASPClient):
	name = "ClearTax"
	required_settings = ("endpoint_url", "client_secret")

	# ------------------------------------------------------------------ connection

	@property
	def timeout(self) -> int:
		return cint(self.config.extra.get("timeout")) or 60

	@property
	def taxpayer_tin(self) -> str:
		return frappe.db.get_value("Company", self.config.company, "uae_tin") or ""

	def _url(self, path: str) -> str:
		return f"{self.config.endpoint_url.rstrip('/')}{path}"

	def _account(self) -> str:
		"""One token per account: changing the endpoint, secret or taxpayer must not reuse the token of
		the old ones. Companies on the same account share it, which matters because a new token
		revokes the old one."""
		account = "|".join([self.config.endpoint_url.rstrip("/"), self.config.client_secret])
		return hashlib.sha256(account.encode()).hexdigest()[:16]

	def _token_key(self) -> str:
		return f"uae_compliance_cleartax_token:{self._account()}"

	def _token(self, refused: str | None = None) -> str:
		"""The shared token. `refused` is a token the API just rejected: it is replaced, unless another
		worker already has."""
		cached = frappe.cache().get_value(self._token_key())
		if cached and cached != refused:
			return cached

		with filelock(f"cleartax_token_{self._account()}", timeout=30):
			cached = frappe.cache().get_value(self._token_key())
			if cached and cached != refused:
				return cached

			token = self._create_token()
			frappe.cache().set_value(self._token_key(), token)
			return token

	def _create_token(self) -> str:
		response = self._send(
			"GET",
			"/integration/v1/authz/token",
			headers={"x-clear-client-secret": self.config.client_secret},
		)
		body = self._json(response)
		token = body.get("access_token") or body.get("access-token")
		if response.status_code != 200 or not token:
			errors = body.get("errors") or []
			detail = "; ".join(
				f"{e.get('error_code')}: {e.get('error_message')}" for e in errors if isinstance(e, dict)
			)
			raise ServiceProviderError(
				_("ClearTax refused the credentials: {0}").format(detail or response.status_code)
			)

		return token

	def _headers(self, token: str) -> dict:
		headers = {
			"x-cleartax-auth-token": token,
			"x-clear-tin": self.taxpayer_tin,
			"x-clear-country-code": "AE",
			"Content-Type": "application/json",
		}
		if self.config.extra.get("trn"):
			headers["x-clear-trn"] = str(self.config.extra["trn"])
		if self.config.extra.get("branch"):
			headers["x-clear-branch"] = str(self.config.extra["branch"])

		return headers

	def _send(self, method: str, path: str, **kwargs):
		"""One HTTP call. Timeouts, throttling and server errors are transient, so they raise errors the
		pipeline retries."""
		try:
			response = requests.request(method, self._url(path), timeout=self.timeout, **kwargs)
		except requests.Timeout as e:
			raise GatewayTimeoutError(_("ClearTax did not answer in time")) from e
		except requests.ConnectionError as e:
			raise ServiceProviderError(_("Could not reach ClearTax: {0}").format(str(e)[:200])) from e

		if response.status_code == 429:
			raise ServiceProviderLimitExceededError(_("ClearTax is rate limiting this account"))
		if response.status_code >= 500:
			raise ServiceProviderError(_("ClearTax failed with HTTP {0}").format(response.status_code))

		return response

	@staticmethod
	def _json(response):
		try:
			return response.json()
		except ValueError:
			return {}

	@staticmethod
	def _refused_token(response) -> bool:
		"""A token that is revoked is answered with 401, and one that is malformed with a bare 404."""
		if response.status_code == 401:
			return True

		if response.status_code == 404:
			try:
				response.json()
			except ValueError:
				return True

		return False

	def _call(self, method: str, path: str, **kwargs):
		"""An authenticated call. A refused token is renewed once. Returns the response."""
		token = self._token()
		response = self._send(method, path, headers=self._headers(token), **kwargs)
		if self._refused_token(response):
			token = self._token(refused=token)
			response = self._send(method, path, headers=self._headers(token), **kwargs)

		if self._refused_token(response) or response.status_code == 403:
			raise ServiceProviderError(
				_("ClearTax refused the credentials or the TIN {0} (HTTP {1})").format(
					self.taxpayer_tin, response.status_code
				)
			)

		return response

	@staticmethod
	def _problems(items) -> list[str]:
		"""Errors as "code: message", with the source when it is not ClearTax's own rules."""
		problems = []
		for item in items or []:
			if not isinstance(item, dict):
				continue

			text = f"{item.get('ErrorCode')}: {item.get('ErrorMessage')}"
			if item.get("Path"):
				text += f" ({item['Path']})"
			if item.get("ErrorSource") and item["ErrorSource"] != "CLEARTAX":
				text += f" [{item['ErrorSource']}]"

			problems.append(text)

		return problems

	# ------------------------------------------------------------------ the interface

	def validate_credentials(self) -> None:
		with filelock(f"cleartax_token_{self._account()}", timeout=30):
			frappe.cache().set_value(self._token_key(), self._create_token())

	def submit(self, document: OutgoingDocument, idempotency_key: str) -> SubmitResult:
		"""Send the invoice. ClearTax identifies a document by its number and has no idempotency key,
		so a number that was sent before is looked up instead of being treated as a failure: that is
		what a retry looks like when the first attempt reached ClearTax but its answer did not reach
		us."""
		payload = {
			"documents": [
				{
					"documentData": base64.b64encode(
						json.dumps(to_payload(document.model)).encode()
					).decode(),
					"documentFormat": "JSON",
					"customFields": {"Internal Number": document.number},
				}
			],
			"schema": SCHEMA,
		}
		response = self._call("POST", "/einvoice/v1/documents/send?einvoice-type=SALES", json=payload)
		body = self._json(response)

		if response.status_code != 200:
			# 400 and 406 are a document ClearTax cannot read: sending it again will not help.
			problems = self._problems(body.get("ErrorDetails")) or [
				body.get("message") or f"HTTP {response.status_code}"
			]
			raise ProviderRejectedError("; ".join(problems))

		results = body.get("DocumentResponses") or []
		if not results:
			problems = self._problems(body.get("ErrorDetails"))
			if problems:
				raise ProviderRejectedError("; ".join(problems))

			raise ServiceProviderError(_("ClearTax did not answer for the document"))

		result = results[0]
		errors = result.get("ErrorDetails") or []
		if any(error.get("ErrorCode") == ALREADY_SENT for error in errors if isinstance(error, dict)):
			return self._find_existing(document)

		reference = result.get("DocumentId")
		if str(result.get("Success")).lower() != "true" or not reference:
			problems = self._problems(errors) or [_("Rejected")]
			raise ProviderRejectedError("; ".join(problems))

		return SubmitResult(
			provider_reference=reference,
			status=STATUS_SUBMITTED,
			raw_response=frappe.as_json(body),
		)

	def _find_existing(self, document: OutgoingDocument) -> SubmitResult:
		"""The document ClearTax already holds under this number, found among the taxpayer's documents
		of the day it was issued. The status of the document decides the result: the earlier attempt
		may be delivered, still on its way, or failed."""
		issued = document.model["issue_date"]
		for row in self._list("SALES", date.fromisoformat(issued), date.fromisoformat(issued)):
			if row.get("DocumentNumber") == document.number and row.get("DocumentId"):
				current = self.get_status(row["DocumentId"])
				return SubmitResult(
					provider_reference=row["DocumentId"],
					status=current.status,
					detail=current.detail or _("Already held by ClearTax"),
					raw_response=current.raw_response,
				)

		raise ProviderRejectedError(
			_(
				"ClearTax says invoice number {0} was sent, but it is not among the taxpayer's invoices of {1}."
			).format(document.number, issued)
		)

	def _list(self, kind: str, start: date, end: date) -> list[dict]:
		"""The documents of a kind (SALES or PURCHASE) issued from `start` to `end`, all pages. A range
		longer than the API allows is read in steps. A listing that failed is an error to retry, not an
		empty page."""
		rows = []
		first = start
		while first <= end:
			last = min(first + timedelta(days=LIST_SPAN_DAYS), end)
			page = 0
			while True:
				response = self._call(
					"GET",
					"/einvoice/v1/documents/query",
					params={
						"start-date": first.isoformat(),
						"end-date": last.isoformat(),
						"einvoice-type": kind,
						"page-number": page,
						"page-size": PAGE_SIZE,
					},
				)
				body = self._json(response)
				if response.status_code != 200 or not isinstance(body.get("Documents"), list):
					raise ServiceProviderError(
						_("ClearTax could not give the list: {0}").format(
							"; ".join(self._problems(body.get("ErrorDetails"))) or response.status_code
						)
					)

				rows.extend(body["Documents"])
				if len(body["Documents"]) < PAGE_SIZE:
					break

				page += 1

			first = last + timedelta(days=1)

		return rows

	def get_status(self, provider_reference: str) -> StatusResult:
		response = self._call(
			"GET", f"/einvoice/v1/documents/{provider_reference}/status", params={"einvoice-type": "SALES"}
		)
		body = self._json(response)
		if response.status_code != 200 or not body.get("Status"):
			raise ServiceProviderError(
				_("ClearTax could not give the status: {0}").format(
					"; ".join(self._problems(body.get("ErrorDetails"))) or response.status_code
				)
			)

		status, detail = map_status(body["Status"], body.get("ReportingDetails"), body.get("ErrorDetails"))
		return StatusResult(status=status, detail=detail, raw_response=frappe.as_json(body))

	def fetch_inbound(self, known_references: set[str] | None = None) -> list[InboundDocument]:
		"""The invoices received in the last `inbound_days` days that are not logged yet, each fetched by
		its number for the lines and the seller's details. Only a validated document is received."""
		known = known_references or set()
		today = date.today()
		start = today - timedelta(days=cint(self.config.extra.get("inbound_days")) or 30)
		documents = []
		for row in self._list("PURCHASE", start, today):
			reference = row.get("DocumentId")
			if not reference or reference in known or row.get("Status") != "Validated":
				continue

			try:
				model = self._inbound_model(row)
			except ServiceProviderLimitExceededError:
				raise
			except ServiceProviderError:
				# Left unlogged, so the next fetch tries it again; the others are still received.
				frappe.log_error(title=f"ClearTax inbound invoice failed: {reference}")
				continue

			documents.append(InboundDocument(provider_reference=reference, model=model))

		return documents

	def _inbound_model(self, row: dict) -> dict:
		"""A received invoice in the shape `inbound.parse_document` gives. The list carries the TINs;
		the invoice itself supplies the rest."""
		response = self._call(
			"GET",
			"/einvoice/v1/documents",
			params={"einvoice-type": "PURCHASE", "document-number": row["DocumentNumber"]},
		)
		invoice = self._json(response)
		if response.status_code != 200 or not invoice.get("id"):
			raise ServiceProviderError(
				_("ClearTax could not give invoice {0}").format(row.get("DocumentNumber"))
			)

		def value(*path):
			node = invoice
			for key in path:
				node = node.get(key) if isinstance(node, dict) else None
			return node

		supplier = value("accountingSupplierParty", "party") or {}
		credit = str(value("invoiceTypeCode", "value") or "") in ("381", "81")
		tax_schemes = supplier.get("partyTaxScheme") or [{}]
		totals = invoice.get("legalMonetaryTotal") or {}
		taxes = invoice.get("taxTotal") or [{}]

		def amount(node):
			return flt((node or {}).get("value"))

		return {
			"kind": "CreditNote" if credit else "Invoice",
			"type_code": str(value("invoiceTypeCode", "value") or ""),
			"number": invoice["id"],
			"uuid": invoice.get("uuid") or "",
			"issue_date": invoice.get("issueDate") or "",
			"currency": invoice.get("documentCurrencyCode") or "AED",
			"seller_tin": row.get("SellerTaxIdentifier") or "",
			"seller_trn": tax_schemes[0].get("companyID") or "",
			"seller_name": (supplier.get("partyLegalEntity") or {}).get("registrationName") or "",
			"buyer_tin": row.get("BuyerTaxIdentifier") or "",
			"buyer_trn": ((value("accountingCustomerParty", "party") or {}).get("partyTaxScheme") or [{}])[
				0
			].get("companyID")
			or "",
			"tax_total": amount(taxes[0].get("taxAmount")),
			"payable": amount(totals.get("taxInclusiveAmount")),
			"taxable": amount(totals.get("taxExclusiveAmount")),
			"lines": len(invoice.get("invoiceLine") or []),
		}


# ---------------------------------------------------------------------- mapping


def map_status(text: str, reporting: list | None, errors: list | None) -> tuple[str, str]:
	"""A ClearTax status as one of ours, with the text to show.

	A failed document is rejected, with the rules or network errors that failed it. A delivered one is
	Cleared once the FTA has accepted the report, and Delivered until then. Anything else (pending,
	submitted to the exchange network) is still on its way. The text varies in case."""
	lowered = (text or "").lower()
	if lowered.startswith("failed"):
		detail = "; ".join(ClearTaxASP._problems(errors)) or text
		return STATUS_REJECTED, detail

	if lowered.startswith("delivered"):
		accepted = any(
			str(item.get("Status") or "").upper() == REPORTED
			for item in reporting or []
			if isinstance(item, dict)
		)
		return (STATUS_CLEARED if accepted else STATUS_DELIVERED), text

	return STATUS_SUBMITTED, text


def _amount(value, currency: str) -> dict:
	return {"value": value, "currencyID": currency}


def _tax_scheme() -> dict:
	return {"id": {"value": "VAT"}}


def _address(details: dict) -> dict:
	return {
		"streetName": details.get("street"),
		"cityName": details.get("city"),
		"countrySubentity": details.get("subdivision"),
		"country": {"identificationCode": {"countryCode": details.get("country") or "AE"}},
	}


def _party(details: dict) -> dict:
	company_id = {"value": details["legal_id"]}
	if details.get("legal_type"):
		company_id["schemeAgencyID"] = LEGAL_REGISTRATION_TYPES.get(details["legal_type"])
	authority = details.get("authority") or details.get("passport_country")
	if authority:
		company_id["schemeAgencyName"] = authority

	return {
		"party": {
			"endPointID": {"schemeID": ENDPOINT_SCHEME, "value": details["endpoint"]},
			"postalAddress": _address(details["address"]),
			"partyTaxScheme": [{"companyID": details["trn"], "taxScheme": _tax_scheme()}],
			"partyLegalEntity": {
				"registrationName": details["legal_name"],
				**({"companyID": company_id} if details.get("legal_id") else {}),
			},
		}
	}


def _tax_category(code: str, rate: float, reason: str | None = None) -> dict:
	category = {"id": code, "taxScheme": _tax_scheme()}
	if code not in NO_RATE_CATEGORIES:
		category["percent"] = rate

	if code == "E" and reason:
		category["taxExemptionReasonCode"] = reason

	return category


def _line(line: dict, currency: str) -> dict:
	classification = {}
	if line.get("item_type_code"):
		classification["commodityCode"] = {"value": line["item_type_code"]}
	if line.get("nature_code"):
		classification["natureCode"] = {"value": line["nature_code"]}
	if line.get("hs_code"):
		classification["itemClassificationCode"] = {"listID": "HS", "value": line["hs_code"]}

	item = {
		"name": line["name"],
		"description": line["description"],
		"classifiedTaxCategory": [
			_tax_category(line["category_code"], line["rate"], line.get("exemption_reason_code"))
		],
	}
	if classification:
		item["commodityClassification"] = [classification]
	if line.get("sac_code"):
		item["additionalItemIdentification"] = {"id": {"value": line["sac_code"], "schemeID": "SAC"}}
	if line.get("gtin"):
		item["standardItemIdentification"] = {"id": {"value": line["gtin"], "schemeID": "0160"}}

	return {
		"id": str(line["id"]),
		"invoicedQuantity": {"quantity": line["quantity"], "unitCode": line["unit_code"]},
		"lineExtensionAmount": _amount(line["net_amount"], currency),
		"item": item,
		"price": {
			"priceAmount": _amount(line["net_price"], currency),
			"baseQuantity": {"quantity": 1, "unitCode": line["unit_code"]},
			"allowanceCharge": {
				"chargeIndicator": "false",
				"amount": _amount(line["discount"], currency),
				"baseAmount": _amount(line["gross_price"], currency),
			},
		},
		"itemPriceExtension": {
			"amount": _amount(line["amount_aed"], "AED"),
			# An exempt line has no VAT amount (rule ibr-163-ae).
			"taxTotal": {"taxAmount": _amount(line["vat_amount_aed"], "AED")}
			if line["vat_amount_aed"] is not None
			else None,
		},
	}


def _clean(value):
	"""Drop empty values, so the document carries only what the invoice has."""
	if isinstance(value, dict):
		return {k: _clean(v) for k, v in value.items() if v not in (None, "", [], {})}
	if isinstance(value, list):
		return [_clean(v) for v in value]

	return value


def to_payload(model: dict) -> dict:
	"""The PINT AE JSON document of an invoice model (see PintAEBuilder.build_all)."""
	currency = model["currency"]
	totals = model["totals"]
	credit = model.get("credit_note") or {}
	period = model.get("invoice_period") or {}
	foreign = bool(model.get("tax_currency"))

	invoice = {
		"customizationID": CUSTOMIZATION_ID,
		"profileID": PROFILE_ID,
		"profileExecutionID": model["transaction_flags"],
		"id": model["number"],
		"uuid": model["uuid"],
		"issueDate": model["issue_date"],
		"issueTime": model["issue_time"][:8],
		"dueDate": model.get("due_date"),
		"taxPointDate": model.get("vat_point_date"),
		"invoiceTypeCode": {"value": model["type_code"]},
		"documentCurrencyCode": currency,
		"taxCurrencyCode": model.get("tax_currency"),
		"buyerReference": model.get("buyer_reference"),
		"accountingSupplierParty": _party(model["seller"]),
		"accountingCustomerParty": _party(model["buyer"]),
		"taxTotal": [
			{
				"taxAmount": _amount(totals["tax_total"], currency),
				"taxSubtotal": [
					{
						"taxableAmount": _amount(entry["taxable"], currency),
						"taxAmount": _amount(entry["tax"], currency),
						"taxCategory": _tax_category(entry["code"], entry["rate"], entry.get("reason")),
					}
					for entry in model["breakdown"]
				],
			}
		],
		"legalMonetaryTotal": {
			"lineExtensionAmount": _amount(totals["line_total"], currency),
			"taxExclusiveAmount": _amount(totals["tax_exclusive"], currency),
			"taxInclusiveAmount": _amount(totals["tax_inclusive"], currency),
			"payableRoundingAmount": _amount(totals["rounding"], currency) if totals["rounding"] else None,
			"payableAmount": _amount(totals["payable"], currency),
		},
		"invoiceLine": [_line(line, currency) for line in model["lines"]],
	}

	if foreign:
		invoice["taxExchangeRate"] = {
			"sourceCurrencyCode": currency,
			"targetCurrencyCode": "AED",
			"calculationRate": model["exchange_rate"],
		}
		invoice["taxTotal"].append({"taxAmount": _amount(totals["tax_total_aed"], "AED")})
		invoice["additionalDocumentReference"] = [
			{
				"id": "AED",
				"documentTypeCode": "aedtotal-incl-vat",
				"documentDescription": f"AED {totals['tax_inclusive_aed']:.2f}",
			}
		]

	if model.get("payment_means_code"):
		invoice["paymentMeans"] = {"paymentMeansCode": {"value": model["payment_means_code"]}}

	if credit:
		invoice["discrepancyResponse"] = {"responseCode": credit.get("reason_code")}
		if credit.get("preceding_number"):
			# A list, and not the `invoiceDocumentReference` of the API document: that form is read but
			# fails rule ibr-055-ae.
			invoice["billingReference"] = [
				{
					"additionalDocumentReference": {
						"id": credit["preceding_number"],
						"issueDate": credit.get("preceding_date"),
					}
				}
			]

	if period:
		invoice["invoicePeriod"] = {
			"startDate": period.get("start"),
			"endDate": period.get("end"),
			"descriptionCode": period.get("frequency"),
		}

	if model.get("principal_id"):
		invoice["sellerSupplierParty"] = {
			"party": {"partyIdentification": [{"id": {"value": model["principal_id"]}}]}
		}

	if model.get("beneficiary_id"):
		invoice["buyerCustomerParty"] = {
			"party": {"partyIdentification": [{"id": {"value": model["beneficiary_id"]}}]}
		}

	delivery = model.get("delivery")
	if delivery:
		invoice["delivery"] = {
			"actualDeliveryDate": delivery["date"],
			"deliveryLocation": {
				"address": {
					"streetName": delivery["street"],
					"cityName": delivery["city"],
					"countrySubentity": delivery["subdivision"],
					"country": {"identificationCode": {"countryCode": delivery["country"]}},
				}
			},
		}

	return _clean(invoice)
