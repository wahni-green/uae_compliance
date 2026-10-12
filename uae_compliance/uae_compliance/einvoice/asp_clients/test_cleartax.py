import base64
import json
from datetime import date
from unittest.mock import MagicMock, patch

import frappe
import requests

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
from uae_compliance.uae_compliance.einvoice.asp_client import OutgoingDocument, ProviderConfig
from uae_compliance.uae_compliance.einvoice.asp_clients.cleartax import (
	ClearTaxASP,
	map_status,
	to_payload,
)
from uae_compliance.uae_compliance.einvoice.exceptions import ProviderRejectedError
from uae_compliance.uae_compliance.einvoice.pint_ae_builder import build_document
from uae_compliance.uae_compliance.einvoice.test_pint_ae import EInvoiceTestCase

TOKEN = {"access_token": "tok-1", "valid_till": None}
REQUEST = "uae_compliance.uae_compliance.einvoice.asp_clients.cleartax.requests.request"


def reply(body, status=200):
	response = MagicMock()
	response.status_code = status
	if body is None:
		response.json.side_effect = ValueError("not json")
	else:
		response.json.return_value = body
	return response


def accepted(reference="doc-1"):
	return {
		"ErrorDetails": None,
		"Success": "true",
		"DocumentResponses": [
			{"DocumentId": reference, "Success": "true", "ErrorDetails": [], "WarningDetails": None}
		],
	}


def failed(code, message, path=None):
	return {
		"Success": "true",
		"DocumentResponses": [
			{
				"DocumentId": None,
				"Success": "false",
				"ErrorDetails": [
					{"ErrorCode": code, "ErrorMessage": message, "ErrorSource": "CLEARTAX", "Path": path}
				],
			}
		],
	}


class TestClearTax(EInvoiceTestCase):
	def setUp(self):
		super().setUp()
		self.provider = ClearTaxASP(
			ProviderConfig(
				company=self.company,
				environment="Sandbox",
				endpoint_url="https://asp.example/",
				client_secret="secret",
			)
		)
		frappe.cache().delete_value(self.provider._token_key())
		self.addCleanup(frappe.cache().delete_value, self.provider._token_key())

	def document(self):
		doc = self.invoice(submit=True)
		xml, _summary, model = build_document(doc)
		return OutgoingDocument(number=doc.name, uuid="u-1", xml=xml, model=model)

	def calls(self, request):
		return [(c.args[0], c.args[1]) for c in request.call_args_list]

	# ---------------------------------------------------------------- authentication

	def test_the_token_is_fetched_once_and_shared(self):
		with patch(REQUEST, side_effect=[reply(TOKEN), reply({}), reply({})]) as request:
			self.provider._call("GET", "/x")
			self.provider._call("GET", "/x")

		self.assertEqual(sum("authz/token" in url for _method, url in self.calls(request)), 1)
		headers = request.call_args_list[1].kwargs["headers"]
		self.assertEqual(headers["x-cleartax-auth-token"], "tok-1")
		self.assertEqual(headers["x-clear-country-code"], "AE")
		self.assertEqual(request.call_args_list[0].kwargs["headers"]["x-clear-client-secret"], "secret")

	def test_trn_and_branch_are_sent_only_when_configured(self):
		self.provider.config.extra = {"trn": "100000000000003", "branch": "Main"}
		headers = self.provider._headers("tok")
		self.assertEqual(headers["x-clear-trn"], "100000000000003")
		self.assertEqual(headers["x-clear-branch"], "Main")

		self.provider.config.extra = {}
		headers = self.provider._headers("tok")
		self.assertNotIn("x-clear-trn", headers)
		self.assertNotIn("x-clear-branch", headers)

	def test_refused_credentials(self):
		errors = {
			"errors": [{"error_code": "CLI-SEC-002", "error_message": "Invalid or inactive client secret."}]
		}
		with patch(REQUEST, return_value=reply(errors, 401)):
			with self.assertRaisesRegex(ServiceProviderError, "CLI-SEC-002"):
				self.provider.validate_credentials()

	def test_a_revoked_token_is_renewed_once(self):
		frappe.cache().set_value(self.provider._token_key(), "old")
		answers = [reply({}, 401), reply({"access_token": "tok-2"}), reply({"Status": "ok"})]
		with patch(REQUEST, side_effect=answers) as request:
			response = self.provider._call("GET", "/x")

		self.assertEqual(response.json(), {"Status": "ok"})
		self.assertEqual(request.call_args.kwargs["headers"]["x-cleartax-auth-token"], "tok-2")

	def test_a_token_renewed_by_another_worker_is_used_instead_of_creating_another(self):
		"""A new token revokes the old one, so two workers must not each create one."""
		frappe.cache().set_value(self.provider._token_key(), "old")
		original = self.provider._send
		state = {"first": True}

		def send(method, path, **kwargs):
			if state["first"]:
				state["first"] = False
				# Another worker renews the token while this call is being refused.
				frappe.cache().set_value(self.provider._token_key(), "new")
				return reply({}, 401)

			return original(method, path, **kwargs)

		with patch.object(self.provider, "_send", side_effect=send):
			with patch(REQUEST, return_value=reply({})) as request:
				self.provider._call("GET", "/x")

		self.assertFalse(any("authz/token" in url for _method, url in self.calls(request)))
		self.assertEqual(request.call_args.kwargs["headers"]["x-cleartax-auth-token"], "new")

	def test_a_malformed_token_is_answered_with_a_bare_404_and_counts_as_refused(self):
		frappe.cache().set_value(self.provider._token_key(), "bad")
		answers = [reply(None, 404), reply({"access_token": "tok-2"}), reply({})]
		with patch(REQUEST, side_effect=answers) as request:
			self.provider._call("GET", "/x")

		self.assertEqual(request.call_args.kwargs["headers"]["x-cleartax-auth-token"], "tok-2")

	def test_a_json_404_is_not_an_authentication_failure(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		with patch(REQUEST, return_value=reply({"ErrorDetails": [{"ErrorCode": "300102"}]}, 404)) as request:
			response = self.provider._call("GET", "/x")

		self.assertEqual(response.status_code, 404)
		self.assertEqual(request.call_count, 1)

	def test_a_403_is_reported_as_a_credential_or_tin_problem(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		with patch(REQUEST, return_value=reply({"ErrorDetails": [{"ErrorCode": "403"}]}, 403)):
			self.assertRaises(ServiceProviderError, self.provider._call, "GET", "/x")

	def test_transient_failures_are_distinguished(self):
		for outcome, error in (
			(requests.Timeout(), GatewayTimeoutError),
			(requests.ConnectionError("down"), ServiceProviderError),
			(reply({}, 429), ServiceProviderLimitExceededError),
			(reply({}, 503), ServiceProviderError),
		):
			effect = outcome if isinstance(outcome, Exception) else None
			with patch(REQUEST, side_effect=effect, return_value=outcome):
				self.assertRaises(error, self.provider._send, "GET", "/x")

	# ---------------------------------------------------------------- submit

	def test_submit_sends_the_invoice_as_base64_json_and_returns_the_document_id(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		document = self.document()
		with patch(REQUEST, return_value=reply(accepted("doc-9"))) as request:
			result = self.provider.submit(document, "key")

		self.assertEqual(result.provider_reference, "doc-9")
		self.assertEqual(result.status, STATUS_SUBMITTED)

		self.assertEqual(
			request.call_args.args,
			("POST", "https://asp.example/einvoice/v1/documents/send?einvoice-type=SALES"),
		)
		body = request.call_args.kwargs["json"]
		self.assertEqual(body["schema"], "CLEAR_UNIFIED_SCHEMA")
		sent = body["documents"][0]
		self.assertEqual(sent["documentFormat"], "JSON")
		self.assertEqual(sent["customFields"], {"Internal Number": document.number})
		invoice = json.loads(base64.b64decode(sent["documentData"]))
		self.assertEqual(invoice["id"], document.number)
		self.assertEqual(invoice["invoiceTypeCode"], {"value": "380"})

	def test_a_rule_failure_found_at_once_is_a_rejection_with_its_rule(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		body = failed("ibr-co-16", "[ibr-co-16]-Amount due", "Invoice.LegalMonetaryTotal[0]")
		with patch(REQUEST, return_value=reply(body)):
			with self.assertRaisesRegex(ProviderRejectedError, r"ibr-co-16.*LegalMonetaryTotal"):
				self.provider.submit(self.document(), "key")

	def test_a_document_that_cannot_be_read_is_a_rejection(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		body = {
			"ErrorDetails": [
				{"ErrorCode": "406", "ErrorMessage": "Cannot deserialize value", "ErrorSource": "CLEARTAX"}
			]
		}
		with patch(REQUEST, return_value=reply(body, 406)):
			with self.assertRaisesRegex(ProviderRejectedError, "Cannot deserialize"):
				self.provider.submit(self.document(), "key")

	def test_an_answer_without_a_document_result_is_transient(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		with patch(REQUEST, return_value=reply({"Success": "true", "DocumentResponses": []})):
			self.assertRaises(ServiceProviderError, self.provider.submit, self.document(), "key")

	def test_a_number_sent_before_is_looked_up_and_takes_its_real_status(self):
		"""What a retry looks like when the first attempt reached ClearTax but its answer was lost."""
		frappe.cache().set_value(self.provider._token_key(), "tok")
		document = self.document()
		listing = {
			"Success": "true",
			"Documents": [
				{"DocumentId": "other", "DocumentNumber": "X-1"},
				{"DocumentId": "held-1", "DocumentNumber": document.number},
			],
		}
		status = {
			"Status": "Delivered to Buyer",
			"ReportingDetails": [{"Status": "ACCEPTED"}],
			"ErrorDetails": [],
		}
		answers = [
			reply(failed("300118", "Submission Request for same uniqueId is in progress")),
			reply(listing),
			reply(status),
		]
		with patch(REQUEST, side_effect=answers) as request:
			result = self.provider.submit(document, "key")

		self.assertEqual(result.provider_reference, "held-1")
		self.assertEqual(result.status, STATUS_CLEARED)
		query = request.call_args_list[1].kwargs["params"]
		self.assertEqual(query["start-date"], document.model["issue_date"])
		self.assertEqual(query["end-date"], document.model["issue_date"])
		self.assertEqual(query["einvoice-type"], "SALES")

	def test_a_number_sent_before_that_failed_is_still_a_rejection_with_the_reasons(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		document = self.document()
		listing = {
			"Success": "true",
			"Documents": [{"DocumentId": "held-2", "DocumentNumber": document.number}],
		}
		status = {
			"Status": "Failed",
			"ErrorDetails": [
				{"ErrorCode": "ibr-136-ae", "ErrorMessage": "Buyer legal id", "ErrorSource": "CLEARTAX"}
			],
		}
		answers = [reply(failed("300118", "in progress")), reply(listing), reply(status)]
		with patch(REQUEST, side_effect=answers):
			result = self.provider.submit(document, "key")

		self.assertEqual(result.status, STATUS_REJECTED)
		self.assertIn("ibr-136-ae", result.detail)

	def test_a_number_that_cannot_be_found_is_a_rejection(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		answers = [reply(failed("300118", "in progress")), reply({"Success": "true", "Documents": []})]
		with patch(REQUEST, side_effect=answers):
			self.assertRaises(ProviderRejectedError, self.provider.submit, self.document(), "key")

	def test_a_failed_lookup_is_retryable_not_a_rejection(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		answers = [reply(failed("300118", "in progress")), reply({"ErrorDetails": []}, 400)]
		with patch(REQUEST, side_effect=answers):
			self.assertRaises(ServiceProviderError, self.provider.submit, self.document(), "key")

	# ---------------------------------------------------------------- the listing

	def test_a_long_range_is_listed_in_steps_the_api_accepts_and_in_pages(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		full = {"Success": "true", "Documents": [{"DocumentId": str(i)} for i in range(100)]}
		last = {"Success": "true", "Documents": [{"DocumentId": "z"}]}
		with patch(REQUEST, side_effect=[reply(full), reply(last), reply(last)]) as request:
			rows = self.provider._list("SALES", date(2026, 10, 1), date(2026, 10, 10))

		self.assertEqual(len(rows), 102)
		params = [c.kwargs["params"] for c in request.call_args_list]
		# Ten days: a first step of seven days (two pages), then the remaining three.
		self.assertEqual(
			(params[0]["start-date"], params[0]["end-date"], params[0]["page-number"]),
			("2026-10-01", "2026-10-07", 0),
		)
		self.assertEqual((params[1]["start-date"], params[1]["page-number"]), ("2026-10-01", 1))
		self.assertEqual((params[2]["start-date"], params[2]["end-date"]), ("2026-10-08", "2026-10-10"))

	def test_a_failed_listing_is_an_error_not_an_empty_page(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		body = {"ErrorDetails": [{"ErrorCode": "400", "ErrorMessage": "Date range must not exceed 7 days"}]}
		with patch(REQUEST, return_value=reply(body, 400)):
			self.assertRaises(
				ServiceProviderError, self.provider._list, "SALES", date(2026, 10, 1), date(2026, 10, 2)
			)

	# ---------------------------------------------------------------- status

	def test_status_mapping(self):
		accepted_report = [{"Status": "ACCEPTED"}]
		for text, reporting, expected in (
			("Pending", None, STATUS_SUBMITTED),
			("Submitted to exchange network", accepted_report, STATUS_SUBMITTED),
			("Delivered to buyer network", [{"Status": "NOT_SUBMITTED"}], STATUS_DELIVERED),
			("Delivered to buyer network", accepted_report, STATUS_CLEARED),
			("Delivered to Buyer", accepted_report, STATUS_CLEARED),
			("delivered to buyer", accepted_report, STATUS_CLEARED),
			("Failed", [{"Status": "NOT_SUBMITTED"}], STATUS_REJECTED),
		):
			self.assertEqual(map_status(text, reporting, None)[0], expected, (text, reporting))

	def test_a_failed_status_carries_the_rules_and_the_network_errors(self):
		errors = [
			{
				"ErrorCode": "ibr-079",
				"ErrorMessage": "Empty elements",
				"ErrorSource": "CLEARTAX",
				"Path": "Invoice.X",
			},
			{
				"ErrorCode": "20001",
				"ErrorMessage": "Not registered in SML",
				"ErrorSource": "PEPPOL",
				"Path": "buyerIdentifier",
			},
		]
		status, detail = map_status("Failed", [{"Status": "WITHDRAWN"}], errors)
		self.assertEqual(status, STATUS_REJECTED)
		self.assertIn("ibr-079: Empty elements (Invoice.X)", detail)
		self.assertIn("20001: Not registered in SML (buyerIdentifier) [PEPPOL]", detail)

	def test_get_status_reads_the_document_status(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		body = {
			"Success": "true",
			"Status": "Delivered to Buyer",
			"ReportingDetails": [{"Status": "ACCEPTED"}],
		}
		with patch(REQUEST, return_value=reply(body)) as request:
			result = self.provider.get_status("doc-1")

		self.assertEqual(result.status, STATUS_CLEARED)
		self.assertTrue(request.call_args.args[1].endswith("/einvoice/v1/documents/doc-1/status"))

	def test_an_unusable_status_answer_is_transient(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		not_found = {"ErrorDetails": [{"ErrorCode": "300102", "ErrorMessage": "No data"}]}
		for answer in (reply(not_found, 404), reply({"Success": "true"})):
			with patch(REQUEST, return_value=answer):
				self.assertRaises(ServiceProviderError, self.provider.get_status, "doc-1")

	# ---------------------------------------------------------------- inbound

	def received(self, number="INV-1", **kwargs):
		return {
			"id": number,
			"uuid": "uuid-1",
			"issueDate": "2026-10-05",
			"invoiceTypeCode": {"value": kwargs.get("type_code", "380")},
			"documentCurrencyCode": "AED",
			"accountingSupplierParty": {
				"party": {
					"partyTaxScheme": [{"companyID": "155555555500003"}],
					"partyLegalEntity": {"registrationName": "Seller LLC"},
				}
			},
			"accountingCustomerParty": {"party": {"partyTaxScheme": [{"companyID": "123456789000003"}]}},
			"taxTotal": [{"taxAmount": {"value": 5.0, "currencyID": "AED"}}],
			"legalMonetaryTotal": {
				"taxExclusiveAmount": {"value": 100.0},
				"taxInclusiveAmount": {"value": 105.0},
			},
			"invoiceLine": [{"id": "1"}, {"id": "2"}],
		}

	def inbound_window(self):
		"""A window of two days, which is one listing call."""
		self.provider.config.extra = {"inbound_days": 1}

	def listed(self, number, reference, status="Validated"):
		return {
			"DocumentId": reference,
			"DocumentNumber": number,
			"SellerTaxIdentifier": "1555555555",
			"BuyerTaxIdentifier": "1234567890",
			"Status": status,
		}

	def test_inbound_skips_known_and_unvalidated_documents_and_reads_the_rest(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		self.inbound_window()
		listing = {
			"Success": "true",
			"Documents": [
				self.listed("INV-1", "new-1"),
				self.listed("INV-2", "known-1"),
				self.listed("INV-3", "bad-1", status="Failed"),
			],
		}
		with patch(REQUEST, side_effect=[reply(listing), reply(self.received("INV-1"))]) as request:
			documents = self.provider.fetch_inbound(known_references={"known-1"})

		self.assertEqual([d.provider_reference for d in documents], ["new-1"])
		model = documents[0].model
		self.assertEqual(model["number"], "INV-1")
		self.assertEqual(model["kind"], "Invoice")
		self.assertEqual(model["issue_date"], "2026-10-05")
		self.assertEqual(model["seller_tin"], "1555555555")
		self.assertEqual(model["seller_trn"], "155555555500003")
		self.assertEqual(model["seller_name"], "Seller LLC")
		self.assertEqual(model["buyer_tin"], "1234567890")
		self.assertEqual(model["buyer_trn"], "123456789000003")
		self.assertEqual((model["taxable"], model["tax_total"], model["payable"]), (100, 5, 105))
		self.assertEqual(model["lines"], 2)
		self.assertEqual(
			request.call_args.kwargs["params"], {"einvoice-type": "PURCHASE", "document-number": "INV-1"}
		)

	def test_a_received_credit_note_is_a_credit_note(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		self.inbound_window()
		listing = {"Success": "true", "Documents": [self.listed("CN-1", "new-2")]}
		with patch(REQUEST, side_effect=[reply(listing), reply(self.received("CN-1", type_code="381"))]):
			documents = self.provider.fetch_inbound()

		self.assertEqual(documents[0].model["kind"], "CreditNote")

	def test_a_failed_detail_fetch_is_skipped_and_the_others_are_received(self):
		frappe.cache().set_value(self.provider._token_key(), "tok")
		self.inbound_window()
		listing = {"Success": "true", "Documents": [self.listed("INV-1", "a"), self.listed("INV-2", "b")]}
		answers = [reply(listing), reply({"ErrorDetails": []}, 404), reply(self.received("INV-2"))]
		with patch(REQUEST, side_effect=answers):
			documents = self.provider.fetch_inbound()

		self.assertEqual([d.provider_reference for d in documents], ["b"])

	# ---------------------------------------------------------------- payload

	def test_the_payload_follows_the_unified_schema(self):
		_xml, _summary, model = build_document(self.invoice(submit=True))
		payload = to_payload(model)

		self.assertEqual(payload["customizationID"], "urn:peppol:pint:billing-1@ae-1")
		self.assertEqual(payload["profileExecutionID"], "00000000")
		self.assertEqual(payload["issueDate"], model["issue_date"])
		self.assertEqual(
			payload["accountingSupplierParty"]["party"]["endPointID"],
			{"schemeID": "0235", "value": model["seller"]["endpoint"]},
		)
		self.assertEqual(
			payload["paymentMeans"], {"paymentMeansCode": {"value": model["payment_means_code"]}}
		)
		totals = payload["legalMonetaryTotal"]
		self.assertEqual(totals["payableAmount"], {"value": model["totals"]["payable"], "currencyID": "AED"})
		self.assertEqual(
			payload["taxTotal"][0]["taxSubtotal"][0]["taxCategory"],
			{"id": "S", "percent": 5, "taxScheme": {"id": {"value": "VAT"}}},
		)

		line = payload["invoiceLine"][0]
		self.assertEqual(line["itemPriceExtension"]["amount"]["currencyID"], "AED")
		self.assertEqual(line["price"]["allowanceCharge"]["chargeIndicator"], "false")
		json.dumps(payload)

	def test_an_exempt_line_has_no_rate_and_no_vat_amount(self):
		doc = self.invoice([{"item_code": "_Test EInv Exempt", "rate": 300, "vat_rate": 0}], submit=True)
		payload = to_payload(build_document(doc)[2])

		line = payload["invoiceLine"][0]
		category = line["item"]["classifiedTaxCategory"][0]
		self.assertEqual(category["id"], "E")
		self.assertNotIn("percent", category)
		self.assertEqual(category["taxExemptionReasonCode"], "DL8.46.1")
		self.assertNotIn("taxTotal", line["itemPriceExtension"])

		subtotal = payload["taxTotal"][0]["taxSubtotal"][0]["taxCategory"]
		self.assertNotIn("percent", subtotal)

	def test_a_credit_note_names_its_original_in_a_list_and_carries_the_reason(self):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		original = self.invoice(submit=True)
		credit = make_return_doc("Sales Invoice", original.name)
		credit.uae_emirate = "Dubai"
		credit.uae_credit_note_reason = "Returned"
		credit.uae_credit_note_reason_code = "DL8.61.1.D"
		credit.items[0].qty = -1
		credit.insert()

		payload = to_payload(build_document(credit)[2])

		self.assertEqual(payload["invoiceTypeCode"], {"value": "381"})
		self.assertEqual(payload["discrepancyResponse"], {"responseCode": "DL8.61.1.D"})
		self.assertEqual(
			payload["billingReference"],
			[
				{
					"additionalDocumentReference": {
						"id": original.name,
						"issueDate": frappe.db.get_value(
							"Sales Invoice", original.name, "posting_date"
						).isoformat(),
					}
				}
			],
		)
		self.assertNotIn("paymentMeans", payload)
		self.assertNotIn("dueDate", payload)

	def test_a_foreign_currency_invoice_carries_the_exchange_rate_and_the_aed_figures(self):
		from uae_compliance.tests import make_customer

		abbr = frappe.get_cached_value("Company", self.company, "abbr")
		account = f"Debtors USD - {abbr}"
		if not frappe.db.exists("Account", account):
			frappe.get_doc(
				{
					"doctype": "Account",
					"account_name": "Debtors USD",
					"company": self.company,
					"parent_account": f"Accounts Receivable - {abbr}",
					"account_type": "Receivable",
					"account_currency": "USD",
				}
			).insert()

		make_customer("_Test UAE Customer", "100987654321003")
		doc = self.invoice(currency="USD", conversion_rate=3.6725, debit_to=account)
		model = build_document(doc)[2]
		payload = to_payload(model)

		self.assertEqual(payload["documentCurrencyCode"], "USD")
		self.assertEqual(payload["taxCurrencyCode"], "AED")
		# The API reads `taxExchangeRate`; the mapping sheet's `pricingExchangeRate` is not accepted.
		self.assertEqual(
			payload["taxExchangeRate"],
			{"sourceCurrencyCode": "USD", "targetCurrencyCode": "AED", "calculationRate": 3.6725},
		)
		self.assertEqual(
			payload["taxTotal"][1],
			{"taxAmount": {"value": model["totals"]["tax_total_aed"], "currencyID": "AED"}},
		)
		self.assertEqual(payload["additionalDocumentReference"][0]["documentTypeCode"], "aedtotal-incl-vat")

	def test_the_period_the_principal_and_the_beneficiary_are_sent(self):
		_xml, _summary, model = build_document(self.invoice(submit=True))
		model["invoice_period"] = {"start": "2026-09-01", "end": "2026-09-30", "frequency": "MTH"}
		model["principal_id"] = "100987654300003"
		model["beneficiary_id"] = "100111222300003"
		payload = to_payload(model)

		self.assertEqual(
			payload["invoicePeriod"],
			{"startDate": "2026-09-01", "endDate": "2026-09-30", "descriptionCode": "MTH"},
		)
		self.assertEqual(
			payload["sellerSupplierParty"]["party"]["partyIdentification"],
			[{"id": {"value": "100987654300003"}}],
		)
		self.assertEqual(
			payload["buyerCustomerParty"]["party"]["partyIdentification"],
			[{"id": {"value": "100111222300003"}}],
		)

	def test_empty_values_are_dropped_but_zero_is_kept(self):
		_xml, _summary, model = build_document(
			self.invoice([{"item_code": "_Test EInv Zero", "rate": 500, "vat_rate": 0}], submit=True)
		)
		payload = to_payload(model)

		self.assertNotIn("taxCurrencyCode", payload)
		self.assertNotIn("invoicePeriod", payload)
		subtotal = payload["taxTotal"][0]["taxSubtotal"][0]
		self.assertEqual(subtotal["taxAmount"]["value"], 0)
		self.assertEqual(subtotal["taxCategory"]["percent"], 0)
