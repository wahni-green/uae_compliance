import json
from unittest.mock import patch

import frappe
from frappe.utils import add_years, getdate
from lxml import etree

from uae_compliance.tests import enable_einvoicing
from uae_compliance.uae_compliance.einvoice import inbound, pipeline
from uae_compliance.uae_compliance.einvoice.pint_ae_builder import NAMESPACES, build_xml
from uae_compliance.uae_compliance.einvoice.test_pipeline import PipelineTestCase

NS = {"cac": NAMESPACES["cac"], "cbc": NAMESPACES["cbc"]}


class TestInbound(PipelineTestCase):
	def _received_xml(self, seller_tin="1555555555", buyer_tin=None) -> str:
		"""An invoice as a supplier would have sent it to the company."""
		xml = etree.fromstring(build_xml(self.invoice())[0])
		seller = xml.xpath("cac:AccountingSupplierParty/cac:Party/cbc:EndpointID", namespaces=NS)[0]
		seller.text = seller_tin
		buyer = xml.xpath("cac:AccountingCustomerParty/cac:Party/cbc:EndpointID", namespaces=NS)[0]
		buyer.text = buyer_tin or frappe.db.get_value("Company", self.company, "uae_tin")
		buyer_trn = xml.xpath(
			"cac:AccountingCustomerParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID", namespaces=NS
		)[0]
		buyer_trn.text = frappe.db.get_value("Company", self.company, "uae_trn")
		return etree.tostring(xml).decode()

	def _enable(self, **documents):
		enable_einvoicing(self.company)
		settings = frappe.get_doc("UAE E-Invoice Settings")
		settings.companies[0].extra_config = json.dumps({"inbound": documents})
		settings.save()
		frappe.clear_document_cache("UAE E-Invoice Settings", "UAE E-Invoice Settings")

	def test_parse_reads_the_header(self):
		details = inbound.parse_document(self._received_xml().encode())

		self.assertEqual(details["kind"], "Invoice")
		self.assertEqual(details["type_code"], "380")
		self.assertEqual(details["seller_tin"], "1555555555")
		self.assertEqual(details["buyer_tin"], "1234567890")
		self.assertEqual(details["currency"], "AED")
		self.assertEqual(details["payable"], 2100)
		self.assertEqual(details["lines"], 1)

	def test_parse_refuses_what_is_not_an_invoice(self):
		self.assertRaises(ValueError, inbound.parse_document, b"<Order/>")
		self.assertRaises(ValueError, inbound.parse_document, b"<Invoice")

	def test_a_document_delivered_as_a_model_is_logged(self):
		from uae_compliance.uae_compliance.einvoice.asp_client import InboundDocument

		model = {
			"kind": "Invoice",
			"type_code": "380",
			"number": "INV-9",
			"uuid": "u-9",
			"issue_date": "2026-10-01",
			"currency": "AED",
			"seller_tin": "1555555555",
			"seller_trn": "",
			"seller_name": "Model Seller",
			"buyer_tin": frappe.db.get_value("Company", self.company, "uae_tin"),
			"buyer_trn": "",
			"tax_total": 5,
			"payable": 105,
			"lines": 1,
		}
		enable_einvoicing(self.company)
		with patch(
			"uae_compliance.uae_compliance.einvoice.asp_clients.mock.MockASP.fetch_inbound",
			return_value=[InboundDocument("MODEL-1", model=model)],
		):
			self.assertEqual(inbound.receive(self.company), 1)

		log = frappe.get_doc("UAE E-Invoice Log", {"provider_reference": "MODEL-1"})
		self.assertEqual((log.status, log.document_number, log.total_amount), ("Delivered", "INV-9", 105))
		self.assertEqual(log.xml, "")
		self.assertEqual(json.loads(log.payload)["seller_name"], "Model Seller")

	def test_references_already_logged_are_passed_to_the_provider(self):
		from uae_compliance.uae_compliance.einvoice.asp_client import InboundDocument

		enable_einvoicing(self.company)
		seen = []

		def fetch(self_, known_references=None):
			seen.append(set(known_references))
			return [
				InboundDocument(
					"KNOWN-1",
					model={
						"kind": "Invoice",
						"number": "A",
						"issue_date": "2026-10-01",
						"seller_tin": "",
						"seller_trn": "",
						"seller_name": "",
						"buyer_tin": "",
						"buyer_trn": "",
						"currency": "AED",
						"payable": 1,
						"uuid": "x",
						"type_code": "380",
						"tax_total": 0,
						"lines": 1,
					},
				)
			]

		with patch("uae_compliance.uae_compliance.einvoice.asp_clients.mock.MockASP.fetch_inbound", fetch):
			inbound.receive(self.company)
			inbound.receive(self.company)

		# Other tests of this class leave documents behind, so only what this one logged is checked.
		self.assertNotIn("KNOWN-1", seen[0])
		self.assertIn("KNOWN-1", seen[1])

	def test_a_received_document_is_logged(self):
		self._enable(**{"REF-1": self._received_xml()})

		self.assertEqual(inbound.receive(self.company), 1)

		log = frappe.get_doc("UAE E-Invoice Log", {"provider_reference": "REF-1"})
		self.assertEqual((log.direction, log.status), ("Inbound", "Delivered"))
		self.assertEqual((log.document_type, str(log.document_date)), ("Invoice", str(self.date)))
		self.assertEqual((log.party_tin, log.total_amount, log.currency), ("1555555555", 2100, "AED"))
		self.assertEqual(log.errors, "")
		self.assertIn("<Invoice", log.xml)

	def test_the_same_document_is_not_logged_twice(self):
		self._enable(**{"REF-2": self._received_xml()})

		self.assertEqual(inbound.receive(self.company), 1)
		self.assertEqual(inbound.receive(self.company), 0)
		self.assertEqual(frappe.db.count("UAE E-Invoice Log", {"provider_reference": "REF-2"}), 1)

	def test_the_sender_is_matched_to_a_supplier_by_tin(self):
		frappe.get_doc(
			{"doctype": "Supplier", "supplier_name": "_Test Sender", "uae_tin": "1555555555"}
		).insert()
		self._enable(**{"REF-3": self._received_xml()})
		inbound.receive(self.company)

		log = frappe.get_doc("UAE E-Invoice Log", {"provider_reference": "REF-3"})
		self.assertEqual(log.supplier, "_Test Sender")

	def test_an_unknown_sender_has_no_supplier(self):
		self._enable(**{"REF-4": self._received_xml(seller_tin="1666666666")})
		inbound.receive(self.company)

		log = frappe.get_doc("UAE E-Invoice Log", {"provider_reference": "REF-4"})
		self.assertFalse(log.supplier)

	def test_a_document_for_someone_else_is_flagged(self):
		self._enable(**{"REF-5": self._received_xml(buyer_tin="1777777777")})
		inbound.receive(self.company)

		log = frappe.get_doc("UAE E-Invoice Log", {"provider_reference": "REF-5"})
		self.assertEqual(log.status, "Invalid")
		self.assertIn("1777777777", log.errors)

	def test_a_document_that_cannot_be_read_is_logged_as_invalid(self):
		self._enable(**{"REF-6": "<not xml"})
		inbound.receive(self.company)

		log = frappe.get_doc("UAE E-Invoice Log", {"provider_reference": "REF-6"})
		self.assertEqual(log.status, "Invalid")
		self.assertTrue(log.errors)

	def _model(self, **changes):
		model = {
			"kind": "Invoice",
			"type_code": "380",
			"number": "INV-X",
			"uuid": "u-x",
			"issue_date": "2026-10-01",
			"currency": "AED",
			"seller_tin": "1555555555",
			"seller_trn": "",
			"seller_name": "Model Seller",
			"buyer_tin": "",
			"buyer_trn": "",
			"tax_total": 0,
			"payable": 1,
			"lines": 1,
		}
		model.update(changes)
		return model

	def _receive_models(self, documents):
		enable_einvoicing(self.company)
		with patch(
			"uae_compliance.uae_compliance.einvoice.asp_clients.mock.MockASP.fetch_inbound",
			return_value=documents,
		):
			return inbound.receive(self.company)

	def test_a_bad_date_is_logged_as_invalid_without_stopping_the_others(self):
		from uae_compliance.uae_compliance.einvoice.asp_client import InboundDocument

		received = self._receive_models(
			[
				InboundDocument("BADDATE-1", model=self._model(issue_date="2026-99-99")),
				InboundDocument("GOOD-1", model=self._model()),
			]
		)

		self.assertEqual(received, 2)
		bad = frappe.get_doc("UAE E-Invoice Log", {"provider_reference": "BADDATE-1"})
		self.assertEqual(bad.status, "Invalid")
		self.assertTrue(bad.retain_until)
		self.assertEqual(
			frappe.db.get_value("UAE E-Invoice Log", {"provider_reference": "GOOD-1"}, "status"), "Delivered"
		)

	def test_a_model_missing_keys_is_logged_as_invalid(self):
		from uae_compliance.uae_compliance.einvoice.asp_client import InboundDocument

		model = self._model()
		del model["seller_name"]
		self._receive_models([InboundDocument("PARTIAL-1", model=model)])

		log = frappe.get_doc("UAE E-Invoice Log", {"provider_reference": "PARTIAL-1"})
		self.assertEqual(log.status, "Invalid")
		self.assertIn("seller_name", log.errors)

	def test_an_unreadable_document_still_has_a_retention_date(self):
		self._enable(**{"REF-8": "<not xml"})
		inbound.receive(self.company)

		log = frappe.get_doc("UAE E-Invoice Log", {"provider_reference": "REF-8"})
		self.assertGreaterEqual(getdate(log.retain_until), add_years(getdate(), 5))
		self.assertRaises(frappe.ValidationError, log.delete)

	def test_a_reference_repeated_in_one_response_is_logged_once(self):
		from uae_compliance.uae_compliance.einvoice.asp_client import InboundDocument

		received = self._receive_models(
			[InboundDocument("DUP-1", model=self._model()), InboundDocument("DUP-1", model=self._model())]
		)

		self.assertEqual(received, 1)
		self.assertEqual(frappe.db.count("UAE E-Invoice Log", {"provider_reference": "DUP-1"}), 1)

	def test_references_of_another_environment_do_not_hide_new_documents(self):
		from uae_compliance.uae_compliance.einvoice.asp_client import InboundDocument

		self._receive_models([InboundDocument("ENV-1", model=self._model())])
		frappe.db.set_value("UAE E-Invoice Log", {"provider_reference": "ENV-1"}, "environment", "Production")

		received = self._receive_models([InboundDocument("ENV-1", model=self._model())])

		self.assertEqual(received, 1)

	def test_received_documents_are_retained(self):
		self._enable(**{"REF-7": self._received_xml()})
		inbound.receive(self.company)

		log = frappe.get_doc("UAE E-Invoice Log", {"provider_reference": "REF-7"})
		self.assertRaises(frappe.ValidationError, log.delete)

	def test_nothing_is_fetched_for_a_company_that_is_not_enabled(self):
		settings = frappe.get_doc("UAE E-Invoice Settings")
		settings.companies = []
		settings.save()
		frappe.clear_document_cache("UAE E-Invoice Settings", "UAE E-Invoice Settings")

		self.assertEqual(inbound.receive(self.company), 0)

	def test_the_scheduler_fetches_inbound_documents(self):
		from unittest.mock import patch

		self._enable(**{"REF-8": self._received_xml()})
		for target in ("commit", "rollback"):
			patcher = patch.object(frappe.db, target)
			patcher.start()
			self.addCleanup(patcher.stop)

		pipeline.process_pending()

		self.assertTrue(frappe.db.exists("UAE E-Invoice Log", {"provider_reference": "REF-8"}))
