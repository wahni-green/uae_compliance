from pathlib import Path
from unittest.mock import patch

import frappe
from lxml import etree

from uae_compliance.tests import make_einvoice_item
from uae_compliance.uae_compliance.einvoice.exceptions import EInvoiceNotSupportedError
from uae_compliance.uae_compliance.einvoice.pint_ae_builder import NAMESPACES, build_document, build_xml
from uae_compliance.uae_compliance.einvoice.test_pint_ae import (
	PINT_RULES_DIR,
	UBL_XSD_DIR,
	EInvoiceTestCase,
	TestAgainstTheOfficialSchematron,
)
from uae_compliance.uae_compliance.einvoice.validators import validate_xml

NS = {"cac": NAMESPACES["cac"], "cbc": NAMESPACES["cbc"]}


def _find(xml, path):
	return xml.xpath(path, namespaces=NS)


def _text(xml, path):
	found = _find(xml, path)
	return found[0].text if found else None


class CasesTestCase(EInvoiceTestCase):
	def setUp(self):
		super().setUp()
		make_einvoice_item("_Test EInv OOS", "Out of Scope")

	def xml(self, doc):
		return etree.fromstring(build_xml(doc)[0])

	def credit_note_of(self, original, item_rate_row=0):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		credit = make_return_doc("Sales Invoice", original.name)
		credit.uae_emirate = "Dubai"
		credit.uae_credit_note_reason = "Returned"
		credit.uae_credit_note_reason_code = "DL8.61.1.D"
		credit.items[0].qty = -1
		credit.insert()
		return credit


class TestOutOfScopeAndDocumentType(CasesTestCase):
	def test_an_out_of_scope_line_has_no_rate_and_no_vat(self):
		doc = self.invoice(
			[
				{"item_code": "_Test EInv Service", "rate": 1000},
				{"item_code": "_Test EInv OOS", "rate": 200, "vat_rate": 0},
			]
		)
		xml = self.xml(doc)

		line = _find(xml, "cac:InvoiceLine")[1]
		self.assertEqual(_text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID"), "O")
		self.assertIsNone(_text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent"))
		# Unlike an exempt line, it states a VAT amount of 0 (rule ibr-104-ae).
		self.assertEqual(_text(line, "cac:ItemPriceExtension/cac:TaxTotal/cbc:TaxAmount"), "0.00")
		breakdown = _find(xml, "cac:TaxTotal/cac:TaxSubtotal[cac:TaxCategory/cbc:ID='O']")[0]
		self.assertIsNone(_text(breakdown, "cac:TaxCategory/cbc:Percent"))
		self.assertEqual(_text(breakdown, "cbc:TaxAmount"), "0.00")
		self.assertEqual(_text(xml, "cbc:InvoiceTypeCode"), "380")
		self.assertEqual(validate_xml(etree.tostring(xml)), [])

	def test_a_document_of_exempt_and_out_of_scope_lines_only_is_type_480(self):
		for item in ("_Test EInv Exempt", "_Test EInv OOS"):
			doc = self.invoice([{"item_code": item, "rate": 300, "vat_rate": 0}])
			xml = self.xml(doc)

			self.assertEqual(_text(xml, "cbc:InvoiceTypeCode"), "480", item)
			self.assertEqual(build_document(doc)[2]["type_code"], "480")
			self.assertEqual(validate_xml(etree.tostring(xml)), [], item)

	def test_a_zero_rated_line_keeps_the_ordinary_type(self):
		doc = self.invoice(
			[
				{"item_code": "_Test EInv Zero", "rate": 300, "vat_rate": 0},
				{"item_code": "_Test EInv Exempt", "rate": 300, "vat_rate": 0},
			]
		)

		self.assertEqual(_text(self.xml(doc), "cbc:InvoiceTypeCode"), "380")

	def test_a_credit_note_of_an_exempt_only_invoice_is_type_81(self):
		original = self.invoice(
			[{"item_code": "_Test EInv Exempt", "rate": 300, "qty": 2, "vat_rate": 0}], submit=True
		)
		xml = self.xml(self.credit_note_of(original))

		self.assertEqual(_text(xml, "cbc:CreditNoteTypeCode"), "81")
		self.assertEqual(validate_xml(etree.tostring(xml)), [])

	def test_the_validator_catches_the_wrong_type_for_the_lines(self):
		doc = self.invoice([{"item_code": "_Test EInv Exempt", "rate": 300, "vat_rate": 0}])
		wrong = build_xml(doc)[0].replace(b">480<", b">380<")

		self.assertTrue(any("480" in e for e in validate_xml(wrong)))


class TestTransactionFlags(CasesTestCase):
	def test_a_free_trade_zone_supply_carries_the_beneficiary(self):
		doc = self.invoice(uae_is_free_zone_supply=1, uae_free_zone_beneficiary_id="189098765401003")
		xml = self.xml(doc)

		self.assertEqual(_text(xml, "cbc:ProfileExecutionID"), "10000000")
		self.assertEqual(
			_text(xml, "cac:BuyerCustomerParty/cac:Party/cac:PartyIdentification/cbc:ID"), "189098765401003"
		)
		self.assertEqual(validate_xml(etree.tostring(xml)), [])

	def test_a_free_trade_zone_supply_without_a_beneficiary_is_invalid(self):
		doc = self.invoice(uae_is_free_zone_supply=1)
		with patch.object(type(doc), "validate", lambda self: None):
			errors = validate_xml(build_xml(doc)[0])

		self.assertTrue(any("beneficiary" in e for e in errors))

	def test_a_deemed_supply_needs_no_due_date(self):
		doc = self.invoice(uae_is_deemed_supply=1)
		xml = self.xml(doc)

		self.assertEqual(_text(xml, "cbc:ProfileExecutionID"), "01000000")
		self.assertEqual(validate_xml(etree.tostring(xml)), [])

	def test_a_deemed_supply_cannot_be_an_exempt_only_document(self):
		doc = self.invoice(
			[{"item_code": "_Test EInv Exempt", "rate": 300, "vat_rate": 0}], uae_is_deemed_supply=1
		)

		self.assertRaises(EInvoiceNotSupportedError, build_xml, doc)

	def test_an_ecommerce_supply_carries_the_delivery_address(self):
		doc = self.invoice(uae_is_ecommerce_supply=1)
		xml = self.xml(doc)

		self.assertEqual(_text(xml, "cbc:ProfileExecutionID"), "00000010")
		address = "cac:Delivery/cac:DeliveryLocation/cac:Address"
		self.assertEqual(_text(xml, f"{address}/cbc:CountrySubentity"), "AUH")
		self.assertTrue(_text(xml, f"{address}/cbc:StreetName"))
		self.assertEqual(validate_xml(etree.tostring(xml)), [])

	def test_an_ecommerce_supply_without_a_delivery_address_is_invalid(self):
		doc = self.invoice(uae_is_ecommerce_supply=1)
		frappe.db.set_value("Address", doc.customer_address, "address_line1", "")

		self.assertTrue(any("delivery" in e for e in validate_xml(build_xml(doc)[0])))

	def test_the_flags_can_combine(self):
		doc = self.invoice(
			uae_is_free_zone_supply=1,
			uae_free_zone_beneficiary_id="189098765401003",
			uae_is_ecommerce_supply=1,
		)

		self.assertEqual(_text(self.xml(doc), "cbc:ProfileExecutionID"), "10000010")


class TestCasesAgainstTheOfficialRules(CasesTestCase):
	def setUp(self):
		super().setUp()
		try:
			import saxonche
		except ImportError:
			self.skipTest("saxonche is not installed")

		if not PINT_RULES_DIR or not Path(PINT_RULES_DIR, "trn-invoice").exists():
			self.skipTest("PINT_AE_RESOURCES_DIR is not set")

	def failures(self, doc, folder="trn-invoice"):
		return TestAgainstTheOfficialSchematron._failures(self, build_xml(doc)[0], folder)

	def test_out_of_scope_mixed_with_standard(self):
		doc = self.invoice(
			[
				{"item_code": "_Test EInv Service", "rate": 1000},
				{"item_code": "_Test EInv OOS", "rate": 200, "vat_rate": 0},
			]
		)
		self.assertEqual(self.failures(doc), [])

	def test_exempt_and_out_of_scope_only(self):
		for item in ("_Test EInv Exempt", "_Test EInv OOS"):
			doc = self.invoice([{"item_code": item, "rate": 300, "vat_rate": 0}])
			self.assertEqual(self.failures(doc), [], item)

	def test_credit_note_of_exempt_only(self):
		original = self.invoice(
			[{"item_code": "_Test EInv Exempt", "rate": 300, "qty": 2, "vat_rate": 0}], submit=True
		)
		self.assertEqual(self.failures(self.credit_note_of(original), "trn-creditnote"), [])

	def test_free_trade_zone_supply(self):
		doc = self.invoice(uae_is_free_zone_supply=1, uae_free_zone_beneficiary_id="189098765401003")
		self.assertEqual(self.failures(doc), [])

	def test_deemed_supply(self):
		self.assertEqual(self.failures(self.invoice(uae_is_deemed_supply=1)), [])

	def test_ecommerce_supply(self):
		self.assertEqual(self.failures(self.invoice(uae_is_ecommerce_supply=1)), [])


class TestCasesAgainstTheUBLSchema(CasesTestCase):
	"""The new elements (BuyerCustomerParty, Delivery) and the 480/81 types must also be valid UBL, in
	the right order."""

	def setUp(self):
		super().setUp()
		if not UBL_XSD_DIR or not Path(UBL_XSD_DIR, "maindoc", "UBL-Invoice-2.1.xsd").exists():
			self.skipTest("UBL_XSD_DIR is not set")

	def assert_valid(self, doc, name="Invoice"):
		schema = etree.XMLSchema(etree.parse(str(Path(UBL_XSD_DIR, "maindoc", f"UBL-{name}-2.1.xsd"))))
		schema.assertValid(etree.fromstring(build_xml(doc)[0]))

	def test_out_of_scope_and_exempt_only_documents(self):
		self.assert_valid(
			self.invoice(
				[
					{"item_code": "_Test EInv Service", "rate": 1000},
					{"item_code": "_Test EInv OOS", "rate": 200, "vat_rate": 0},
				]
			)
		)
		self.assert_valid(self.invoice([{"item_code": "_Test EInv Exempt", "rate": 300, "vat_rate": 0}]))

	def test_credit_note_of_an_exempt_only_invoice(self):
		original = self.invoice(
			[{"item_code": "_Test EInv Exempt", "rate": 300, "qty": 2, "vat_rate": 0}], submit=True
		)
		self.assert_valid(self.credit_note_of(original), "CreditNote")

	def test_free_trade_zone_deemed_and_ecommerce_supplies(self):
		self.assert_valid(
			self.invoice(uae_is_free_zone_supply=1, uae_free_zone_beneficiary_id="189098765401003")
		)
		self.assert_valid(self.invoice(uae_is_deemed_supply=1))
		self.assert_valid(self.invoice(uae_is_ecommerce_supply=1))
		self.assert_valid(
			self.invoice(
				uae_is_free_zone_supply=1,
				uae_free_zone_beneficiary_id="189098765401003",
				uae_is_ecommerce_supply=1,
			)
		)
