from pathlib import Path
from unittest.mock import patch

import frappe
from lxml import etree

from uae_compliance.tests import make_einvoice_item
from uae_compliance.uae_compliance.constants.vat_return import REVERSE_CHARGE_SUPPLY_CATEGORY
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
from uae_compliance.uae_compliance.utils.vat_return import get_invoice_rows

NS = {"cac": NAMESPACES["cac"], "cbc": NAMESPACES["cbc"]}
GTIN = "6291041500213"


def _find(xml, path):
	return xml.xpath(path, namespaces=NS)


def _text(xml, path):
	found = _find(xml, path)
	return found[0].text if found else None


class ReverseChargeTestCase(EInvoiceTestCase):
	def setUp(self):
		super().setUp()
		item = make_einvoice_item("_Test EInv RC Goods")
		frappe.db.set_value("Item", item.name, "is_stock_item", 0)
		if not frappe.db.exists("Item Barcode", {"parent": item.name, "barcode": GTIN}):
			item.reload()
			item.append("barcodes", {"barcode": GTIN})
			item.save()

	def rc_invoice(self, rc_type="Electronic Devices", submit=False, **kwargs):
		values = {
			"uae_is_reverse_charge": 1,
			"uae_reverse_charge_type": rc_type,
			"uae_rc_declaration": 1,
			"taxes": [],
			**kwargs,
		}
		return self.invoice(
			[{"item_code": "_Test EInv RC Goods", "rate": 500, "qty": 3}], submit=submit, **values
		)

	def xml(self, doc):
		return etree.fromstring(build_xml(doc)[0])

	def credit_note_of(self, original):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		credit = make_return_doc("Sales Invoice", original.name)
		credit.uae_emirate = "Dubai"
		credit.uae_credit_note_reason = "Returned"
		credit.uae_credit_note_reason_code = "DL8.61.1.D"
		credit.items[0].qty = -1
		credit.insert()
		return credit


class TestReverseChargeSale(ReverseChargeTestCase):
	def test_a_valid_reverse_charge_invoice_carries_no_vat(self):
		doc = self.rc_invoice()

		self.assertEqual(doc.total_taxes_and_charges, 0)
		self.assertEqual(doc.grand_total, 1500)

	def test_the_declarations_must_be_held(self):
		with self.assertRaises(frappe.ValidationError):
			self.rc_invoice(uae_rc_declaration=0)

	def test_the_type_must_be_chosen(self):
		with self.assertRaises(frappe.ValidationError):
			self.rc_invoice(rc_type=None)

	def test_the_recipient_must_be_registered(self):
		frappe.db.set_value("Customer", "_Test UAE Customer", "uae_trn", "")
		with self.assertRaises(frappe.ValidationError):
			self.rc_invoice()

	def test_vat_cannot_be_charged(self):
		with self.assertRaises(frappe.ValidationError):
			self.rc_invoice(
				taxes=[
					{
						"charge_type": "On Net Total",
						"account_head": self.output,
						"description": "VAT",
						"rate": 5,
					}
				]
			)

	def test_it_cannot_be_zero_rated_or_an_export(self):
		with self.assertRaises(frappe.ValidationError):
			self.invoice(
				[{"item_code": "_Test EInv Zero", "rate": 100, "vat_rate": 0}],
				uae_is_reverse_charge=1,
				uae_reverse_charge_type="Natural Gas",
				uae_rc_declaration=1,
				taxes=[],
			)

	def test_it_is_never_a_simplified_invoice(self):
		doc = self.rc_invoice()

		self.assertFalse(doc.uae_is_simplified_tax_invoice)

	def test_the_rows_keep_the_sale_but_no_box_reports_it(self):
		self.rc_invoice(submit=True)

		rows = get_invoice_rows("Sales Invoice", self.company, self.date, self.date)
		self.assertEqual({row.category for row in rows}, {REVERSE_CHARGE_SUPPLY_CATEGORY})

		vat_return = frappe.get_doc(
			{
				"doctype": "UAE VAT Return",
				"company": self.company,
				"from_date": self.date,
				"to_date": self.date,
			}
		).insert()
		vat_return.generate_return()
		self.assertEqual(vat_return.total_due_tax, 0)
		self.assertEqual(sum(row.amount for row in vat_return.boxes if row.box_code != "8"), 0)

	def test_it_counts_as_a_taxable_supply_for_the_recovery_ratio(self):
		self.rc_invoice(submit=True)
		self.invoice([{"item_code": "_Test EInv Exempt", "rate": 1500, "vat_rate": 0}], submit=True)

		vat_return = frappe.get_doc(
			{
				"doctype": "UAE VAT Return",
				"company": self.company,
				"from_date": self.date,
				"to_date": self.date,
			}
		).insert()
		vat_return.generate_return()

		self.assertEqual(vat_return.taxable_supplies_value, 1500)
		self.assertEqual(vat_return.exempt_supplies_value, 1500)
		self.assertEqual(vat_return.recovery_ratio, 50)

	def test_the_audit_file_lists_it_with_the_reverse_charge_code(self):
		from uae_compliance.uae_compliance.utils.faf import generate_faf

		doc = self.rc_invoice(submit=True)
		line = next(
			row for row in generate_faf(self.company, self.date, self.date).splitlines() if doc.name in row
		)

		self.assertIn(",RC", line.replace('"', "").replace(", ", ","))

	def test_the_sales_register_lists_it_outside_every_box(self):
		from uae_compliance.uae_compliance.report.uae_vat_sales_register.uae_vat_sales_register import execute

		doc = self.rc_invoice(submit=True)
		data = execute({"company": self.company, "from_date": self.date, "to_date": self.date})[1]

		entry = next(row for row in data if row["invoice"] == doc.name)
		self.assertEqual(entry["box"], "")
		self.assertEqual(entry["category"], REVERSE_CHARGE_SUPPLY_CATEGORY)
		self.assertEqual(entry["vat_amount"], 0)


class TestReverseChargeDocument(ReverseChargeTestCase):
	def test_the_line_is_category_ae_at_the_standard_rate_with_no_vat(self):
		xml = self.xml(self.rc_invoice())

		line = _find(xml, "cac:InvoiceLine")[0]
		self.assertEqual(_text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID"), "AE")
		self.assertEqual(_text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent"), "5")
		self.assertEqual(_text(line, "cac:ItemPriceExtension/cac:TaxTotal/cbc:TaxAmount"), "0.00")
		self.assertEqual(_text(line, "cac:Item/cac:CommodityClassification/cbc:NatureCode"), "DL8.48.8.2")
		gtin = _find(line, "cac:Item/cac:StandardItemIdentification/cbc:ID")[0]
		self.assertEqual((gtin.text, gtin.get("schemeID")), (GTIN, "0160"))

		breakdown = _find(xml, "cac:TaxTotal/cac:TaxSubtotal")[0]
		self.assertEqual(_text(breakdown, "cac:TaxCategory/cbc:ID"), "AE")
		self.assertEqual(_text(breakdown, "cbc:TaxAmount"), "0.00")
		self.assertEqual(_text(xml, "cac:TaxTotal/cbc:TaxAmount"), "0.00")
		self.assertEqual(_text(xml, "cac:LegalMonetaryTotal/cbc:PayableAmount"), "1500.00")
		self.assertEqual(_text(xml, "cbc:InvoiceTypeCode"), "380")
		self.assertEqual(validate_xml(etree.tostring(xml)), [])

	def test_each_item_s_barcodes_are_read_once(self):
		doc = self.invoice(
			[
				{"item_code": "_Test EInv RC Goods", "rate": 500, "qty": 1},
				{"item_code": "_Test EInv RC Goods", "rate": 400, "qty": 1},
			],
			uae_is_reverse_charge=1,
			uae_reverse_charge_type="Electronic Devices",
			uae_rc_declaration=1,
			taxes=[],
		)
		real = frappe.get_all
		calls = []

		def counting(doctype, *args, **kwargs):
			if doctype == "Item Barcode":
				calls.append(kwargs.get("filters"))
			return real(doctype, *args, **kwargs)

		with patch("frappe.get_all", counting):
			build_document(doc)

		self.assertEqual(len(calls), 1)

	def test_each_type_has_its_code(self):
		for rc_type, code in (
			("Crude or Refined Oil", "DL8.48.3.1"),
			("Natural Gas", "DL8.48.3.2"),
			("Pure Hydrocarbons", "DL8.48.3.3"),
			("Electronic Devices", "DL8.48.8.2"),
			("Precious Metals and Stones", "DL8.48.8.1"),
		):
			xml = self.xml(self.rc_invoice(rc_type))
			self.assertEqual(_text(xml, "//cbc:NatureCode"), code, rc_type)

	def test_metal_scrap_cannot_be_sent(self):
		self.assertRaises(EInvoiceNotSupportedError, build_xml, self.rc_invoice("Metal Scrap"))

	def test_an_item_without_a_gtin_is_invalid(self):
		frappe.db.delete("Item Barcode", {"parent": "_Test EInv RC Goods"})
		errors = validate_xml(build_xml(self.rc_invoice())[0])

		self.assertTrue(any("GTIN" in e for e in errors))

	def test_the_buyer_s_trn_is_required(self):
		doc = self.rc_invoice()
		frappe.db.set_value("Customer", "_Test UAE Customer", "uae_trn", "")
		errors = validate_xml(build_xml(doc)[0])

		self.assertTrue(any("TRN" in e for e in errors))

	def test_a_credit_note_of_a_reverse_charge_invoice(self):
		original = self.rc_invoice(submit=True)
		xml = self.xml(self.credit_note_of(original))

		self.assertEqual(_text(xml, "cbc:CreditNoteTypeCode"), "381")
		self.assertEqual(_text(xml, "//cac:ClassifiedTaxCategory/cbc:ID"), "AE")
		self.assertEqual(validate_xml(etree.tostring(xml)), [])

	def test_the_provider_payload(self):
		payload = to_payload(build_document(self.rc_invoice())[2])

		item = payload["items"][0]
		self.assertEqual(item["invoicedItemTaxCategoryCode"], "AE")
		self.assertEqual(item["typeOfGoodsOrServicesSubjectToRCM"], "DL8.48.8.2")
		self.assertEqual(item["itemStandardIdentifier"], GTIN)
		self.assertEqual(item["vatLineAmount"], 0.0)
		self.assertEqual(payload["invoiceDetail"]["taxableReverseCharge"], 1500.0)
		self.assertEqual(payload["invoiceDetail"]["taxAmountReverseCharge"], 0.0)


class TestReverseChargeAgainstTheOfficialRules(ReverseChargeTestCase):
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

	def test_every_supported_type(self):
		for rc_type in (
			"Crude or Refined Oil",
			"Natural Gas",
			"Pure Hydrocarbons",
			"Electronic Devices",
			"Precious Metals and Stones",
		):
			self.assertEqual(self.failures(self.rc_invoice(rc_type)), [], rc_type)

	def test_credit_note(self):
		original = self.rc_invoice(submit=True)
		self.assertEqual(self.failures(self.credit_note_of(original), "trn-creditnote"), [])


class TestReverseChargeAgainstTheUBLSchema(ReverseChargeTestCase):
	def setUp(self):
		super().setUp()
		if not UBL_XSD_DIR or not Path(UBL_XSD_DIR, "maindoc", "UBL-Invoice-2.1.xsd").exists():
			self.skipTest("UBL_XSD_DIR is not set")

	def schema(self, name):
		return etree.XMLSchema(etree.parse(str(Path(UBL_XSD_DIR, "maindoc", f"UBL-{name}-2.1.xsd"))))

	def test_invoice_and_credit_note(self):
		doc = self.rc_invoice(submit=True)
		self.schema("Invoice").assertValid(etree.fromstring(build_xml(doc)[0]))
		self.schema("CreditNote").assertValid(etree.fromstring(build_xml(self.credit_note_of(doc))[0]))
