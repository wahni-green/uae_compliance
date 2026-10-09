import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, add_years, getdate, now_datetime

from uae_compliance.tests import (
	enable_einvoicing,
	make_customer,
	make_einvoice_item,
	make_sales_invoice,
)
from uae_compliance.uae_compliance.einvoice import pipeline
from uae_compliance.uae_compliance.einvoice.asp_client import SubmitResult
from uae_compliance.uae_compliance.einvoice.exceptions import EInvoiceError, ProviderRejectedError
from uae_compliance.uae_compliance.einvoice.test_pint_ae import EInvoiceTestCase


class PipelineTestCase(EInvoiceTestCase):
	def setUp(self):
		super().setUp()
		enable_einvoicing(self.company)

	def submit(self, **kwargs):
		"""A submitted invoice, with the background job it queues captured instead of run."""
		with patch("frappe.enqueue") as enqueue:
			doc = self.invoice(submit=True, **kwargs)

		return doc, enqueue

	def log_of(self, doc):
		return pipeline.get_log(doc.name)

	def settle(self, log, polls=2):
		pipeline.submit_log(log.name)
		for _ in range(polls):
			pipeline.poll_log(log.name)

		return frappe.get_doc("UAE E-Invoice Log", log.name)


class TestScope(PipelineTestCase):
	def test_nothing_happens_when_the_company_has_not_enabled_it(self):
		frappe.get_doc("UAE E-Invoice Settings").companies = []
		settings = frappe.get_doc("UAE E-Invoice Settings")
		settings.companies = []
		settings.save()
		frappe.clear_document_cache("UAE E-Invoice Settings", "UAE E-Invoice Settings")

		doc, enqueue = self.submit()

		self.assertIsNone(self.log_of(doc))
		enqueue.assert_not_called()

	def test_sales_to_individuals_are_out_of_scope(self):
		frappe.db.set_value("Customer", "_Test UAE Customer", "customer_type", "Individual")
		doc, enqueue = self.submit()

		self.assertIsNone(self.log_of(doc))
		enqueue.assert_not_called()

	def test_invoices_before_the_start_date_are_left_alone(self):
		enable_einvoicing(self.company, mandatory_from=frappe.utils.add_days(self.date, 10))
		doc, _enqueue = self.submit()

		self.assertIsNone(self.log_of(doc))

	def test_invoices_from_the_start_date_are_sent(self):
		enable_einvoicing(self.company, mandatory_from=self.date)
		doc, _enqueue = self.submit()

		self.assertIsNotNone(self.log_of(doc))


class TestSubmission(PipelineTestCase):
	def test_submitting_an_invoice_logs_and_queues_it(self):
		doc, enqueue = self.submit()
		log = self.log_of(doc)

		self.assertEqual(log.status, "Generated")
		self.assertEqual(log.direction, "Outbound")
		self.assertEqual(log.provider, "Mock")
		self.assertTrue(log.xml.startswith("<?xml"))
		model = json.loads(log.payload)
		self.assertEqual((model["number"], model["type_code"]), (doc.name, "380"))
		self.assertEqual(model["totals"]["payable"], 2100)
		self.assertTrue(log.uuid)
		self.assertEqual(log.uuid, frappe.db.get_value("Sales Invoice", doc.name, "uae_einvoice_uuid"))
		self.assertEqual(frappe.db.get_value("Sales Invoice", doc.name, "uae_einvoice_status"), "Generated")
		self.assertEqual(frappe.db.get_value("Sales Invoice", doc.name, "uae_einvoice_log"), log.name)
		self.assertEqual(enqueue.call_args.kwargs["log"], log.name)
		self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])

	def test_an_invoice_that_would_be_invalid_is_not_issued(self):
		frappe.db.set_value("Company", self.company, "uae_legal_registration_id", "")
		with patch("frappe.enqueue"):
			with self.assertRaises(EInvoiceError) as ctx:
				self.invoice(submit=True)

		self.assertIn("legal registration identifier", str(ctx.exception))

	def test_an_unsupported_invoice_is_issued_and_logged_as_invalid(self):
		doc = self.invoice()
		doc.uae_is_margin_scheme = 1
		doc.flags.ignore_validate = True
		with patch("frappe.enqueue") as enqueue:
			doc.submit()

		log = self.log_of(doc)
		self.assertEqual(log.status, "Invalid")
		self.assertIn("margin scheme", log.errors)
		enqueue.assert_not_called()

	def test_retention_runs_five_years_from_the_invoice_date(self):
		doc, _enqueue = self.submit()
		self.assertEqual(self.log_of(doc).retain_until, add_years(getdate(doc.posting_date), 5))


class TestSendingAndPolling(PipelineTestCase):
	def test_a_document_goes_through_to_cleared(self):
		doc, _enqueue = self.submit()
		log = self.log_of(doc)

		pipeline.submit_log(log.name)
		log.reload()
		self.assertEqual(log.status, "Submitted")
		self.assertEqual(log.provider_reference, f"MOCK-{log.idempotency_key}")
		self.assertEqual(log.attempts, 1)

		pipeline.poll_log(log.name)
		log.reload()
		self.assertEqual(log.status, "Delivered")

		pipeline.poll_log(log.name)
		log.reload()
		self.assertEqual(log.status, "Cleared")
		self.assertTrue(log.cleared_on)
		self.assertEqual(frappe.db.get_value("Sales Invoice", doc.name, "uae_einvoice_status"), "Cleared")
		self.assertGreaterEqual(getdate(log.retain_until), add_years(getdate(), 5))

	def test_the_provider_receives_both_the_xml_and_the_model(self):
		doc, _enqueue = self.submit()
		log = self.log_of(doc)

		with patch(
			"uae_compliance.uae_compliance.einvoice.asp_clients.mock.MockASP.submit",
			return_value=SubmitResult("REF", "Submitted"),
		) as submit:
			pipeline.submit_log(log.name)

		document, key = submit.call_args.args
		self.assertEqual((document.number, document.uuid), (doc.name, log.uuid))
		self.assertTrue(document.xml.startswith(b"<?xml"))
		self.assertEqual(document.model["seller"]["trn"], "100123456789003")
		self.assertEqual(document.model["lines"][0]["net_amount"], 2000)
		self.assertEqual(key, log.idempotency_key)

	def test_sending_twice_does_not_send_twice(self):
		doc, _enqueue = self.submit()
		log = self.log_of(doc)
		pipeline.submit_log(log.name)

		with patch("uae_compliance.uae_compliance.einvoice.asp_clients.mock.MockASP.submit") as submit:
			pipeline.submit_log(log.name)

		submit.assert_not_called()

	def test_a_rejected_document_ends_as_rejected(self):
		enable_einvoicing(self.company, behavior="reject")
		doc, _enqueue = self.submit()
		log = self.settle(self.log_of(doc), polls=1)

		self.assertEqual(log.status, "Rejected")

	def test_a_refusal_when_sending_is_final(self):
		doc, _enqueue = self.submit()
		log = self.log_of(doc)

		with patch(
			"uae_compliance.uae_compliance.einvoice.asp_clients.mock.MockASP.submit",
			side_effect=ProviderRejectedError("Buyer unknown"),
		):
			pipeline.submit_log(log.name)

		log.reload()
		self.assertEqual(log.status, "Rejected")
		self.assertIn("Buyer unknown", log.errors)

	def test_a_timeout_is_retried_with_backoff_and_then_fails(self):
		enable_einvoicing(self.company, behavior="timeout")
		doc, _enqueue = self.submit()
		log = self.log_of(doc)

		pipeline.submit_log(log.name)
		log.reload()
		self.assertEqual((log.status, log.attempts), ("Generated", 1))
		self.assertGreater(log.next_attempt_on, now_datetime())

		pipeline.submit_log(log.name)
		log.reload()
		self.assertEqual((log.status, log.attempts), ("Generated", 2))

		pipeline.submit_log(log.name)  # the third and last attempt (the limit is 3)
		log.reload()
		self.assertEqual((log.status, log.attempts), ("Failed", 3))
		self.assertFalse(log.next_attempt_on)
		self.assertIn("timed out", log.errors)

	def test_retry_after_a_failure_sends_again(self):
		enable_einvoicing(self.company, behavior="timeout")
		doc, _enqueue = self.submit()
		log = self.log_of(doc)
		for _ in range(3):
			pipeline.submit_log(log.name)

		enable_einvoicing(self.company, behavior="clear")
		pipeline.retry_log(log.name)

		log.reload()
		self.assertEqual(log.status, "Submitted")
		self.assertEqual(log.attempts, 1)

	def test_retry_rebuilds_the_xml_after_the_data_is_fixed(self):
		doc, _enqueue = self.submit()
		log = self.log_of(doc)
		frappe.db.set_value("Company", self.company, "uae_legal_registration_id", "")
		pipeline.prepare(log)
		log.reload()
		self.assertEqual(log.status, "Invalid")

		frappe.db.set_value("Company", self.company, "uae_legal_registration_id", "112345678900003")
		pipeline.retry_log(log.name)

		log.reload()
		self.assertEqual(log.status, "Submitted")
		self.assertEqual(log.errors, "")

	def test_a_sent_document_cannot_be_retried(self):
		doc, _enqueue = self.submit()
		log = self.settle(self.log_of(doc), polls=1)

		self.assertRaises(frappe.ValidationError, pipeline.retry_log, log.name)


class TestScheduler(PipelineTestCase):
	def setUp(self):
		super().setUp()
		# process_pending commits between documents and rolls back a failed one. Keep the test's data
		# in its own transaction instead of writing it to the site.
		for target in ("commit", "rollback"):
			patcher = patch.object(frappe.db, target)
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_due_documents_are_sent_and_sent_ones_polled(self):
		first, _e1 = self.submit()
		log = self.log_of(first)
		frappe.db.set_value(
			"UAE E-Invoice Log", log.name, "next_attempt_on", add_to_date(now_datetime(), minutes=-1)
		)

		# One run sends it and then checks it, so it is already Delivered; the next run clears it.
		pipeline.process_pending()
		self.assertEqual(frappe.db.get_value("UAE E-Invoice Log", log.name, "status"), "Delivered")

		pipeline.process_pending()
		self.assertEqual(frappe.db.get_value("UAE E-Invoice Log", log.name, "status"), "Cleared")

	def test_a_retry_that_is_not_due_yet_waits(self):
		doc, _enqueue = self.submit()
		log = self.log_of(doc)
		frappe.db.set_value(
			"UAE E-Invoice Log", log.name, "next_attempt_on", add_to_date(now_datetime(), minutes=30)
		)

		pipeline.process_pending()

		self.assertEqual(frappe.db.get_value("UAE E-Invoice Log", log.name, "status"), "Generated")

	def test_one_failing_document_does_not_stop_the_others(self):
		doc, _enqueue = self.submit()
		log = self.log_of(doc)
		frappe.db.set_value(
			"UAE E-Invoice Log", log.name, "next_attempt_on", add_to_date(now_datetime(), minutes=-1)
		)

		# The job rolls its own work back and commits between documents; keep the test's data.
		with (
			patch.object(pipeline, "submit_log", side_effect=RuntimeError("boom")),
			patch("frappe.log_error") as log_error,
		):
			pipeline.process_pending()  # must not raise

		frappe.db.rollback.assert_called_once()
		self.assertIn(log.name, str(log_error.call_args))


class TestCancellation(PipelineTestCase):
	def test_a_sent_invoice_cannot_be_cancelled(self):
		doc, _enqueue = self.submit()
		self.settle(self.log_of(doc), polls=0)

		doc.reload()
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.cancel()
		self.assertIn("credit note", str(ctx.exception))

	def test_an_invoice_that_was_never_sent_can_be_cancelled(self):
		doc, _enqueue = self.submit()
		doc.reload()
		doc.cancel()

		self.assertEqual(doc.docstatus, 2)


class TestRetention(PipelineTestCase):
	def test_a_log_cannot_be_deleted_during_retention(self):
		doc, _enqueue = self.submit()
		log = self.log_of(doc)

		self.assertRaises(frappe.ValidationError, log.delete)

	def test_a_log_can_be_deleted_after_retention(self):
		doc, _enqueue = self.submit()
		log = self.log_of(doc)
		frappe.db.set_value(
			"UAE E-Invoice Log", log.name, "retain_until", frappe.utils.add_days(getdate(), -1)
		)
		log.reload()

		log.delete()
		self.assertFalse(frappe.db.exists("UAE E-Invoice Log", log.name))


class TestCreditNote(PipelineTestCase):
	def test_a_credit_note_is_sent(self):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		original, _enqueue = self.submit()
		credit = make_return_doc("Sales Invoice", original.name)
		credit.uae_emirate = "Dubai"
		credit.uae_credit_note_reason = "Returned"
		credit.uae_credit_note_reason_code = "DL8.61.1.D"
		credit.items[0].qty = -1
		credit.insert()
		with patch("frappe.enqueue"):
			credit.submit()

		log = self.log_of(credit)
		self.assertEqual(log.status, "Generated")
		self.assertIn("CreditNote", log.xml)

	def test_a_credit_note_without_a_reason_code_is_not_issued(self):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		original, _enqueue = self.submit()
		credit = make_return_doc("Sales Invoice", original.name)
		credit.uae_emirate = "Dubai"
		credit.uae_credit_note_reason = "Returned"
		credit.items[0].qty = -1
		credit.insert()

		with patch("frappe.enqueue"), self.assertRaises(EInvoiceError):
			credit.submit()


class TestSimplifiedFlag(PipelineTestCase):
	def test_an_einvoicing_company_never_flags_a_simplified_invoice(self):
		make_customer("_Test Retail Customer")
		make_einvoice_item("_Test Small Item")
		doc = make_sales_invoice(
			[{"item_code": "_Test Small Item", "rate": 10}],
			customer="_Test Retail Customer",
			posting_date=self.date,
		)
		doc.insert()
		self.assertFalse(doc.uae_is_simplified_tax_invoice)
