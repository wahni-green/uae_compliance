from pathlib import Path

import frappe
from lxml import etree

from uae_compliance.uae_compliance.einvoice.asp_clients.microvista import to_payload
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


class MarginTestCase(EInvoiceTestCase):
	def margin_invoice(self, rows=None, vat=None, submit=False):
		"""A margin scheme invoice: the row rate is the price before the VAT on the margin."""
		rows = rows or [{"item_code": "_Test EInv Service", "rate": 1000, "uae_margin_purchase_price": 600}]
		if vat is None:
			vat = round(sum(max(0, row["rate"] - row["uae_margin_purchase_price"]) for row in rows) * 0.05, 2)

		taxes = [
			{"charge_type": "Actual", "account_head": self.output, "description": "VAT", "tax_amount": vat}
		]
		return self.invoice(rows, submit=submit, uae_is_margin_scheme=1, taxes=taxes)

	def xml(self, doc):
		return etree.fromstring(build_xml(doc)[0])

	def credit_note_of(self, original, vat):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		credit = make_return_doc("Sales Invoice", original.name)
		credit.uae_emirate = "Dubai"
		credit.uae_credit_note_reason = "Returned"
		credit.uae_credit_note_reason_code = "DL8.61.1.D"
		credit.taxes = []
		credit.append(
			"taxes",
			{"charge_type": "Actual", "account_head": self.output, "description": "VAT", "tax_amount": -vat},
		)
		credit.insert()
		return credit


class TestMarginSchemeDocument(MarginTestCase):
	def test_the_line_is_the_price_in_category_n_with_no_vat_stated(self):
		xml = self.xml(self.margin_invoice())

		self.assertEqual(_text(xml, "cbc:ProfileExecutionID"), "00100000")
		self.assertEqual(_text(xml, "cbc:InvoiceTypeCode"), "380")
		line = _find(xml, "cac:InvoiceLine")[0]
		self.assertEqual(_text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID"), "N")
		self.assertEqual(_text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent"), "5")
		# 1000 before the VAT on the margin, which is 5% of (1000 - 600) = 20.
		self.assertEqual(_text(line, "cbc:LineExtensionAmount"), "1020.00")
		self.assertEqual(_text(line, "cbc:Note"), "Margin scheme goods")
		self.assertEqual(_text(line, "cac:ItemPriceExtension/cbc:Amount"), "1020.00")
		self.assertEqual(_text(line, "cac:ItemPriceExtension/cac:TaxTotal/cbc:TaxAmount"), "0.00")

		breakdown = _find(xml, "cac:TaxTotal/cac:TaxSubtotal")
		self.assertEqual(len(breakdown), 1)
		self.assertEqual(_text(breakdown[0], "cac:TaxCategory/cbc:ID"), "N")
		self.assertEqual(_text(breakdown[0], "cbc:TaxAmount"), "0.00")
		self.assertEqual(_text(xml, "cac:TaxTotal/cbc:TaxAmount"), "0.00")
		self.assertEqual(_text(xml, "cac:LegalMonetaryTotal/cbc:PayableAmount"), "1020.00")
		self.assertEqual(validate_xml(etree.tostring(xml)), [])

	def test_the_rows_add_up_to_the_invoice_total(self):
		doc = self.margin_invoice(
			[
				{"item_code": "_Test EInv Service", "rate": 1000, "uae_margin_purchase_price": 600},
				{"item_code": "_Test EInv Service", "rate": 333.33, "uae_margin_purchase_price": 100},
				{"item_code": "_Test EInv Service", "rate": 50, "uae_margin_purchase_price": 80},
			]
		)

		xml = self.xml(doc)
		lines = [float(_text(line, "cbc:LineExtensionAmount")) for line in _find(xml, "cac:InvoiceLine")]

		self.assertAlmostEqual(sum(lines), doc.grand_total, places=2)
		# A row sold at a loss owes no VAT: it is its net amount.
		self.assertEqual(lines[2], 50.0)
		self.assertEqual(validate_xml(etree.tostring(xml)), [])

	def test_only_standard_rated_rows_are_allowed(self):
		doc = self.margin_invoice()
		doc.items[0].uae_vat_category = "Zero Rated"

		self.assertRaises(EInvoiceNotSupportedError, build_xml, doc)

	def test_a_credit_note_of_a_margin_invoice(self):
		original = self.margin_invoice(submit=True)
		xml = self.xml(self.credit_note_of(original, 20))

		self.assertEqual(_text(xml, "cbc:CreditNoteTypeCode"), "381")
		self.assertEqual(_text(xml, "cbc:ProfileExecutionID"), "00100000")
		self.assertEqual(_text(xml, "//cac:ClassifiedTaxCategory/cbc:ID"), "N")
		self.assertEqual(_text(xml, "cac:LegalMonetaryTotal/cbc:PayableAmount"), "1020.00")
		self.assertEqual(validate_xml(etree.tostring(xml)), [])

	def test_the_validator_ties_category_n_to_the_margin_flag(self):
		xml = build_xml(self.margin_invoice())[0]

		self.assertTrue(any("margin" in e for e in validate_xml(xml.replace(b"00100000", b"00000000"))))
		ordinary = build_xml(self.invoice())[0].replace(b"<cbc:ID>S</cbc:ID>", b"<cbc:ID>N</cbc:ID>")
		self.assertTrue(any("margin" in e for e in validate_xml(ordinary)))

	def test_the_provider_payload(self):
		payload = to_payload(build_document(self.margin_invoice())[2])

		self.assertEqual(payload["invoice"]["invoiceTransactionTypeCode"], "00100000")
		item = payload["items"][0]
		self.assertEqual(item["invoicedItemTaxCategoryCode"], "N")
		self.assertEqual(item["invoiceLineNetAmount"], 1020.0)
		self.assertEqual(item["vatLineAmount"], 0.0)
		self.assertEqual(payload["invoiceDetail"]["taxableAdditionalVat"], 1020.0)
		self.assertEqual(payload["invoiceDetail"]["taxAmountAdditionalVat"], 0.0)


class TestMarginSchemeAgainstTheOfficialRules(MarginTestCase):
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

	def test_invoice(self):
		self.assertEqual(self.failures(self.margin_invoice()), [])

	def test_invoice_with_several_rows(self):
		doc = self.margin_invoice(
			[
				{"item_code": "_Test EInv Service", "rate": 1000, "uae_margin_purchase_price": 600},
				{"item_code": "_Test EInv Service", "rate": 500, "uae_margin_purchase_price": 700},
			]
		)
		self.assertEqual(self.failures(doc), [])

	def test_credit_note(self):
		original = self.margin_invoice(submit=True)
		self.assertEqual(self.failures(self.credit_note_of(original, 20), "trn-creditnote"), [])


class TestMarginSchemeAgainstTheUBLSchema(MarginTestCase):
	def setUp(self):
		super().setUp()
		if not UBL_XSD_DIR or not Path(UBL_XSD_DIR, "maindoc", "UBL-Invoice-2.1.xsd").exists():
			self.skipTest("UBL_XSD_DIR is not set")

	def test_invoice_and_credit_note(self):
		def schema(name):
			return etree.XMLSchema(etree.parse(str(Path(UBL_XSD_DIR, "maindoc", f"UBL-{name}-2.1.xsd"))))

		original = self.margin_invoice(submit=True)
		schema("Invoice").assertValid(etree.fromstring(build_xml(original)[0]))
		schema("CreditNote").assertValid(etree.fromstring(build_xml(self.credit_note_of(original, 20))[0]))
