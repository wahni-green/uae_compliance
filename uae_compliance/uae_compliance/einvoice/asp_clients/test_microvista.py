import json
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
from uae_compliance.uae_compliance.einvoice.asp_clients.microvista import (
	MicrovistaASP,
	map_status,
	to_payload,
)
from uae_compliance.uae_compliance.einvoice.exceptions import ProviderRejectedError
from uae_compliance.uae_compliance.einvoice.pint_ae_builder import build_document
from uae_compliance.uae_compliance.einvoice.test_pint_ae import EInvoiceTestCase

TOKEN = {"success": True, "data": {"access_token": "tok-1"}}
POST = "uae_compliance.uae_compliance.einvoice.asp_clients.microvista.requests.post"


def reply(body, status=200):
	response = MagicMock()
	response.status_code = status
	response.json.return_value = body
	return response


class TestMicrovista(EInvoiceTestCase):
	def setUp(self):
		super().setUp()
		self.provider = MicrovistaASP(
			ProviderConfig(
				company=self.company,
				environment="Sandbox",
				endpoint_url="https://asp.example/",
				client_id="api-secret",
				client_secret="secret-key",
				extra={"client_code": "CC1"},
			)
		)
		frappe.cache().delete_value(self.provider._token_key())
		self.addCleanup(frappe.cache().delete_value, self.provider._token_key())

	def document(self):
		doc = self.invoice(submit=True)
		xml, _summary, model = build_document(doc)
		return OutgoingDocument(number=doc.name, uuid="u-1", xml=xml, model=model)

	def calls(self, post):
		return [c.args[0] for c in post.call_args_list]

	# ---------------------------------------------------------------- authentication

	def test_the_token_is_fetched_once_and_cached(self):
		with patch(POST, side_effect=[reply(TOKEN), reply({"success": True, "data": {}})] * 2) as post:
			self.provider._call("get-invoice-status", json={})
			self.provider._call("get-invoice-status", json={})

		self.assertEqual(sum("generate-authtoken" in url for url in self.calls(post)), 1)
		headers = post.call_args_list[1].kwargs["headers"]
		self.assertEqual(headers["Authorization"], "Bearer tok-1")
		self.assertEqual(headers["x-clientCode"], "CC1")

	def test_refused_credentials(self):
		with patch(POST, return_value=reply({"success": False, "message": "Bad key"})):
			self.assertRaises(ServiceProviderError, self.provider.validate_credentials)

	def test_a_rejected_token_is_renewed_once(self):
		answers = [reply(TOKEN), reply({}, 401), reply({"success": True, "data": {"access_token": "tok-2"}})]
		answers.append(reply({"success": True, "data": {}}))
		with patch(POST, side_effect=answers) as post:
			body = self.provider._call("get-invoice-status", json={})

		self.assertTrue(body["success"])
		self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer tok-2")

	def test_transient_failures_are_distinguished(self):
		for outcome, error in (
			(requests.Timeout(), GatewayTimeoutError),
			(requests.ConnectionError("down"), ServiceProviderError),
			(reply({}, 429), ServiceProviderLimitExceededError),
			(reply({}, 503), ServiceProviderError),
		):
			effect = outcome if isinstance(outcome, Exception) else None
			with patch(POST, side_effect=effect, return_value=outcome):
				self.assertRaises(error, self.provider._send, "/x")

	# ---------------------------------------------------------------- submit

	def test_submit_returns_the_invoice_id(self):
		document = self.document()
		ok = {"success": True, "statusCode": 1, "data": "inv-1", "message": "Invoice saved successfully."}
		with patch(POST, side_effect=[reply(TOKEN), reply(ok)]) as post:
			result = self.provider.submit(document, "key")

		self.assertEqual(result.provider_reference, "inv-1")
		self.assertEqual(result.status, STATUS_SUBMITTED)
		sent = post.call_args.kwargs["json"]
		self.assertEqual(sent["invoice"]["invoiceNumber"], document.number)

	def test_a_validation_failure_is_a_rejection(self):
		failed = {
			"success": False,
			"statusCode": 3,
			"message": "Validation failed",
			"data": [{"message": "Buyer TRN is invalid"}],
		}
		with patch(POST, side_effect=[reply(TOKEN), reply(failed)]):
			with self.assertRaisesRegex(ProviderRejectedError, "Buyer TRN is invalid"):
				self.provider.submit(self.document(), "key")

	def test_a_bad_request_is_a_rejection(self):
		with patch(POST, side_effect=[reply(TOKEN), reply({"status": 400, "message": "Nope"})]):
			self.assertRaises(ProviderRejectedError, self.provider.submit, self.document(), "key")

	def test_a_missing_invoice_id_is_transient(self):
		with patch(POST, side_effect=[reply(TOKEN), reply({"success": True, "statusCode": 1})]):
			self.assertRaises(ServiceProviderError, self.provider.submit, self.document(), "key")

	def test_a_duplicate_number_is_recovered(self):
		document = self.document()
		duplicate = {
			"success": False,
			"statusCode": 3,
			"data": [{"message": "Invoice number already exists"}],
		}
		listing = {
			"data": {
				"paginationData": [
					{"invoiceNumber": "OTHER", "invoiceMasterId": "x"},
					{
						"invoiceNumber": document.number,
						"invoiceMasterId": "inv-9",
						"invoiceStatus": 200,
						"invoiceStatusText": "Delivered Successfully",
					},
				]
			}
		}
		status = {
			"success": True,
			"data": {"invoicestatuscode": 200, "invoicestatus": "Delivered", "ftastatus": "Delivered"},
		}
		with patch(POST, side_effect=[reply(TOKEN), reply(duplicate), reply(listing), reply(status)]):
			result = self.provider.submit(document, "key")

		self.assertEqual(result.provider_reference, "inv-9")
		self.assertEqual(result.status, STATUS_CLEARED)

	def test_a_recovered_invoice_not_yet_at_the_fta_is_not_cleared(self):
		document = self.document()
		duplicate = {"success": False, "statusCode": 3, "data": ["Invoice number already exists"]}
		listing = {
			"data": {"paginationData": [{"invoiceNumber": document.number, "invoiceMasterId": "inv-9"}]}
		}
		status = {
			"success": True,
			"data": {"invoicestatuscode": 200, "invoicestatus": "Delivered", "ftastatus": "Pending"},
		}
		with patch(POST, side_effect=[reply(TOKEN), reply(duplicate), reply(listing), reply(status)]):
			result = self.provider.submit(document, "key")

		self.assertEqual(result.status, STATUS_DELIVERED)

	def test_a_duplicate_that_cannot_be_found_is_a_rejection(self):
		duplicate = {"success": False, "statusCode": 3, "data": ["Invoice number already exists"]}
		listing = {"data": {"paginationData": []}}
		with patch(POST, side_effect=[reply(TOKEN), reply(duplicate), reply(listing)]):
			self.assertRaises(ProviderRejectedError, self.provider.submit, self.document(), "key")

	# ---------------------------------------------------------------- status

	def test_status_mapping(self):
		self.assertEqual(map_status(200, "Delivered Successfully", "Delivered")[0], STATUS_CLEARED)
		self.assertEqual(map_status(200, "Delivered", None)[0], STATUS_CLEARED)
		self.assertEqual(map_status(200, "Delivered", "Pending", "Delivered")[0], STATUS_DELIVERED)
		self.assertEqual(map_status(3, "Failed at ASP", None)[0], STATUS_REJECTED)
		self.assertEqual(map_status(5, "", None)[0], STATUS_REJECTED)
		self.assertEqual(map_status(None, "Failed validation", None)[0], STATUS_REJECTED)
		self.assertEqual(map_status(1, "Saved", None)[0], STATUS_SUBMITTED)

	def test_get_status_cleared(self):
		status = {
			"success": True,
			"data": {
				"invoicestatuscode": 200,
				"invoicestatus": "Delivered Successfully",
				"ftastatus": "Delivered",
			},
		}
		with patch(POST, side_effect=[reply(TOKEN), reply(status)]) as post:
			result = self.provider.get_status("inv-1")

		self.assertEqual(result.status, STATUS_CLEARED)
		self.assertEqual(post.call_args.kwargs["params"], {"invoiceId": "inv-1"})

	def test_a_failed_status_carries_the_rule_errors(self):
		status = {"success": True, "data": {"invoicestatuscode": 3, "invoicestatus": "Failed"}}
		errors = {"data": [{"errorId": "ibr-001-ae", "errorText": "Something wrong"}]}
		with patch(POST, side_effect=[reply(TOKEN), reply(status), reply(errors)]):
			result = self.provider.get_status("inv-1")

		self.assertEqual(result.status, STATUS_REJECTED)
		self.assertEqual(result.detail, "ibr-001-ae: Something wrong")

	def test_an_unusable_status_answer_is_transient(self):
		with patch(POST, side_effect=[reply(TOKEN), reply({"success": False, "message": "x"})]):
			self.assertRaises(ServiceProviderError, self.provider.get_status, "inv-1")

	# ---------------------------------------------------------------- inbound

	def test_inbound_skips_known_references_and_reads_the_rest(self):
		listing = {
			"data": {
				"paginationData": [
					{"invoiceMasterId": "known"},
					{
						"invoiceMasterId": "new-1",
						"invoiceNumber": "S-1",
						"invoiceType": "380",
						"invoiceDate": "05-10-2026",
						"sellerElectronicID": "1555555555",
						"buyerElectronicID": "1234567890",
						"taxAmount": 5,
						"totalAmount": 105,
					},
				]
			}
		}
		detail = {"success": True, "data": {"Invoice": {"invoiceCurrencyCode": "AED"}, "Items": [{}, {}]}}
		with patch(POST, side_effect=[reply(TOKEN), reply(listing), reply(detail)]):
			documents = self.provider.fetch_inbound({"known"})

		self.assertEqual([d.provider_reference for d in documents], ["new-1"])
		model = documents[0].model
		self.assertEqual(model["issue_date"], "2026-10-05")
		self.assertEqual(model["lines"], 2)
		self.assertEqual(model["payable"], 105)
		self.assertEqual(model["kind"], "Invoice")

	def test_a_failed_detail_fetch_is_not_logged_as_an_empty_invoice(self):
		listing = {"data": {"paginationData": [{"invoiceMasterId": "new-2"}]}}
		with patch(POST, side_effect=[reply(TOKEN), reply(listing), reply({"success": False})]):
			self.assertRaises(ServiceProviderError, self.provider.fetch_inbound, set())

	# ---------------------------------------------------------------- configuration

	def test_a_missing_client_code_is_reported(self):
		self.provider.config.extra = {}
		with patch(POST) as post, self.assertRaisesRegex(ServiceProviderError, "client_code"):
			self.provider.validate_credentials()

		post.assert_not_called()

	def test_a_changed_account_does_not_reuse_the_old_token(self):
		old = self.provider._token_key()
		self.provider.config.client_secret = "another-key"

		self.assertNotEqual(self.provider._token_key(), old)

	# ---------------------------------------------------------------- payload

	def test_payload_keeps_required_buyer_keys_and_drops_other_empties(self):
		_xml, _summary, model = build_document(self.invoice(submit=True))
		payload = to_payload(model)

		for key in (
			"emailID",
			"postCode",
			"buyerCode",
			"contactNo",
			"addressLine2",
			"passportIssuingCountryCode",
		):
			self.assertIn(key, payload["buyer"])

		self.assertEqual(payload["invoice"]["invoiceNumber"], model["number"])
		json.dumps(payload)
