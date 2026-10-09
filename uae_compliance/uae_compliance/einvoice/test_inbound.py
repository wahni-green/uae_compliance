import json

import frappe
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
