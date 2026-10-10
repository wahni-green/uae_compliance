import os
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from lxml import etree

from uae_compliance.tests import (
	configure_vat_settings,
	create_submitted_sales_invoice,
	get_uae_test_company,
	get_unique_test_date,
	make_einvoice_item,
	make_sales_invoice,
	setup_einvoice_masters,
)
from uae_compliance.uae_compliance.einvoice.exceptions import (
	EInvoiceError,
	EInvoiceNotSupportedError,
)
from uae_compliance.uae_compliance.einvoice.pint_ae_builder import NAMESPACES, build_xml
from uae_compliance.uae_compliance.einvoice.validators import raise_if_invalid, validate_xml

NS = {"cac": NAMESPACES["cac"], "cbc": NAMESPACES["cbc"]}

# The OASIS UBL 2.1 schemas are not bundled with the app. Point this at the unpacked `xsd` folder of
# UBL-2.1.zip to also check the element order against the schema.
UBL_XSD_DIR = os.environ.get("UBL_XSD_DIR")


def _find(xml, path):
	return xml.xpath(path, namespaces=NS)


def _text(xml, path):
	found = _find(xml, path)
	return found[0].text if found else None


class EInvoiceTestCase(FrappeTestCase):
	def setUp(self):
		self.company = get_uae_test_company()
		self.output, self.input = configure_vat_settings(self.company)
		self.addresses = setup_einvoice_masters(self.company)
		self.date = get_unique_test_date()
		make_einvoice_item("_Test EInv Service")
		make_einvoice_item("_Test EInv Zero", "Zero Rated")
		make_einvoice_item("_Test EInv Exempt", "Exempt", uae_exemption_reason_code="DL8.46.1")

	def invoice(self, rows=None, submit=False, **kwargs):
		rows = rows or [{"item_code": "_Test EInv Service", "rate": 1000, "qty": 2}]
		kwargs = {
			"customer": "_Test UAE Customer",
			"posting_date": self.date,
			"company_address": self.addresses["company_address"],
			"customer_address": self.addresses["customer_address"],
			"uae_emirate": "Dubai",
			**kwargs,
		}
		if submit:
			return create_submitted_sales_invoice(rows, **kwargs)

		doc = make_sales_invoice(rows, **kwargs)
		doc.insert()
		return doc

	def build(self, doc):
		xml_bytes, summary = build_xml(doc)
		return etree.fromstring(xml_bytes), xml_bytes, summary


class TestBuilder(EInvoiceTestCase):
	def test_standard_invoice_header(self):
		doc = self.invoice()
		xml, _bytes, summary = self.build(doc)

		self.assertEqual(xml.tag, "{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice")
		self.assertEqual(_text(xml, "cbc:CustomizationID"), "urn:peppol:pint:billing-1@ae-1")
		self.assertEqual(_text(xml, "cbc:ProfileID"), "urn:peppol:bis:billing")
		self.assertEqual(_text(xml, "cbc:ProfileExecutionID"), "00000000")
		self.assertEqual(_text(xml, "cbc:ID"), doc.name)
		self.assertEqual(_text(xml, "cbc:UUID"), doc.uae_einvoice_uuid)
		self.assertEqual(_text(xml, "cbc:InvoiceTypeCode"), "380")
		self.assertEqual(_text(xml, "cbc:DocumentCurrencyCode"), "AED")
		self.assertRegex(_text(xml, "cbc:IssueTime"), r"^\d\d:\d\d:\d\d\+04:00$")
		self.assertEqual(summary["type_code"], "380")

	def test_parties(self):
		xml, _bytes, _summary = self.build(self.invoice())

		seller = "cac:AccountingSupplierParty/cac:Party"
		self.assertEqual(_text(xml, f"{seller}/cbc:EndpointID"), "1234567890")
		self.assertEqual(_find(xml, f"{seller}/cbc:EndpointID")[0].get("schemeID"), "0235")
		self.assertEqual(_text(xml, f"{seller}/cac:PartyTaxScheme/cbc:CompanyID"), "100123456789003")
		self.assertEqual(_text(xml, f"{seller}/cac:PostalAddress/cbc:CountrySubentity"), "DXB")
		legal = _find(xml, f"{seller}/cac:PartyLegalEntity/cbc:CompanyID")[0]
		self.assertEqual((legal.text, legal.get("schemeAgencyID")), ("112345678900003", "TL"))
		self.assertEqual(legal.get("schemeAgencyName"), "Dubai Economy")

		buyer = "cac:AccountingCustomerParty/cac:Party"
		self.assertEqual(_text(xml, f"{buyer}/cbc:EndpointID"), "1987654321")
		self.assertEqual(_text(xml, f"{buyer}/cac:PostalAddress/cbc:CountrySubentity"), "AUH")

	def test_line_and_totals(self):
		xml, _bytes, summary = self.build(self.invoice())

		line = _find(xml, "cac:InvoiceLine")[0]
		self.assertEqual(_text(line, "cbc:LineExtensionAmount"), "2000.00")
		self.assertEqual(_text(line, "cbc:InvoicedQuantity"), "2")
		self.assertEqual(_text(line, "cac:Price/cbc:PriceAmount"), "1000")
		self.assertEqual(_text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID"), "S")
		self.assertEqual(_text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent"), "5")
		self.assertEqual(_text(line, "cac:ItemPriceExtension/cbc:Amount"), "2100.00")
		self.assertEqual(_text(line, "cac:ItemPriceExtension/cac:TaxTotal/cbc:TaxAmount"), "100.00")

		self.assertEqual(_text(xml, "cac:TaxTotal/cbc:TaxAmount"), "100.00")
		self.assertEqual(_text(xml, "cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount"), "2100.00")
		self.assertEqual(_text(xml, "cac:LegalMonetaryTotal/cbc:PayableAmount"), "2100.00")
		self.assertEqual(summary["payable"], 2100)

	def test_service_line_classification(self):
		xml, _bytes, _summary = self.build(self.invoice())
		line = _find(xml, "cac:InvoiceLine")[0]

		self.assertEqual(_text(line, "cac:Item/cac:CommodityClassification/cbc:CommodityCode"), "S")
		code = _find(line, "cac:Item/cac:AdditionalItemIdentification/cbc:ID")[0]
		self.assertEqual((code.text, code.get("schemeID")), ("998311", "SAC"))
		self.assertEqual(_find(line, "cac:Item/cac:CommodityClassification/cbc:ItemClassificationCode"), [])

	def test_goods_use_the_hs_code(self):
		make_einvoice_item(
			"_Test EInv Goods", is_stock_item=0, uae_item_type="Goods", customs_tariff_number="84713000"
		)
		xml, _bytes, _summary = self.build(self.invoice([{"item_code": "_Test EInv Goods", "rate": 100}]))
		code = _find(xml, "cac:InvoiceLine/cac:Item/cac:CommodityClassification/cbc:ItemClassificationCode")[
			0
		]
		self.assertEqual((code.text, code.get("listID")), ("84713000", "HS"))

	def test_zero_rated_and_exempt_lines(self):
		doc = self.invoice(
			[
				{"item_code": "_Test EInv Service", "rate": 100},
				{"item_code": "_Test EInv Zero", "rate": 200, "vat_rate": 0},
				{"item_code": "_Test EInv Exempt", "rate": 300, "vat_rate": 0},
			]
		)
		xml, _bytes, _summary = self.build(doc)

		categories = {
			_text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID") for line in _find(xml, "cac:InvoiceLine")
		}
		self.assertEqual(categories, {"S", "Z", "E"})

		subtotals = {
			_text(s, "cac:TaxCategory/cbc:ID"): s for s in _find(xml, "cac:TaxTotal/cac:TaxSubtotal")
		}
		self.assertEqual(_text(subtotals["S"], "cbc:TaxAmount"), "5.00")
		self.assertEqual(_text(subtotals["Z"], "cac:TaxCategory/cbc:Percent"), "0")
		self.assertEqual(_text(subtotals["E"], "cac:TaxCategory/cbc:TaxExemptionReasonCode"), "DL8.46.1")

		exempt = next(
			line
			for line in _find(xml, "cac:InvoiceLine")
			if _text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID") == "E"
		)
		self.assertEqual(_find(exempt, "cac:ItemPriceExtension/cac:TaxTotal"), [])

	def test_export_flag_and_predefined_endpoint(self):
		from uae_compliance.tests import make_address

		abroad = make_address("_Test Export Addr", "India", customer="_Test UAE Customer")
		frappe.db.set_value("Customer", "_Test UAE Customer", "uae_tin", "")
		doc = self.invoice(
			[{"item_code": "_Test EInv Zero", "rate": 500, "vat_rate": 0}],
			customer_address=abroad.name,
			shipping_address_name=abroad.name,
		)
		xml, _bytes, _summary = self.build(doc)

		self.assertEqual(_text(xml, "cbc:ProfileExecutionID"), "00000001")
		self.assertEqual(_text(xml, "cac:AccountingCustomerParty/cac:Party/cbc:EndpointID"), "9900000099")
		self.assertEqual(
			_text(
				xml,
				"cac:AccountingCustomerParty/cac:Party/cac:PostalAddress/cac:Country/cbc:IdentificationCode",
			),
			"IN",
		)

	def test_buyer_without_a_tin_uses_the_not_on_network_endpoint(self):
		frappe.db.set_value("Customer", "_Test UAE Customer", "uae_tin", "")
		xml, _bytes, _summary = self.build(self.invoice())
		self.assertEqual(_text(xml, "cac:AccountingCustomerParty/cac:Party/cbc:EndpointID"), "9900000098")

	def test_supply_date_becomes_the_vat_point_date_only_when_earlier(self):
		later = self.invoice(uae_supply_date=frappe.utils.add_days(self.date, -3))
		xml, _bytes, _summary = self.build(later)
		self.assertEqual(_text(xml, "cbc:TaxPointDate"), str(frappe.utils.add_days(self.date, -3)))

		same = self.invoice()
		xml, _bytes, _summary = self.build(same)
		self.assertIsNone(_text(xml, "cbc:TaxPointDate"))

	def test_the_uuid_is_kept_between_builds(self):
		doc = self.invoice()
		first = self.build(doc)[2]["uuid"]
		second = self.build(doc)[2]["uuid"]
		self.assertEqual(first, second)

	def test_a_company_not_in_aed_is_refused(self):
		doc = self.invoice()
		original = frappe.db.get_value("Company", self.company, "default_currency")
		frappe.db.set_value("Company", self.company, "default_currency", "USD")
		frappe.clear_document_cache("Company", self.company)
		self.addCleanup(lambda: frappe.db.set_value("Company", self.company, "default_currency", original))
		self.addCleanup(frappe.clear_document_cache, "Company", self.company)

		self.assertRaises(EInvoiceNotSupportedError, build_xml, doc)

	def test_out_of_scope_rows_are_refused(self):
		from uae_compliance.tests import make_item

		make_item("_Test EInv Out", "Out of Scope")
		doc = self.invoice([{"item_code": "_Test EInv Out", "rate": 100, "vat_rate": 0}])
		with self.assertRaises(EInvoiceNotSupportedError) as ctx:
			build_xml(doc)
		self.assertIn("Out of Scope", str(ctx.exception))

	def test_margin_scheme_invoices_are_refused(self):
		doc = self.invoice()
		doc.uae_is_margin_scheme = 1
		self.assertRaises(EInvoiceNotSupportedError, build_xml, doc)


class TestDocumentModel(EInvoiceTestCase):
	def test_the_model_carries_the_same_figures_as_the_xml(self):
		from uae_compliance.uae_compliance.einvoice.pint_ae_builder import build_document

		doc = self.invoice(
			[
				{"item_code": "_Test EInv Service", "rate": 100, "qty": 3},
				{"item_code": "_Test EInv Exempt", "rate": 300, "vat_rate": 0},
			]
		)
		xml_bytes, summary, model = build_document(doc)

		self.assertEqual(model["uuid"], summary["uuid"])
		self.assertEqual(model["totals"]["payable"], summary["payable"])
		self.assertEqual(model["transaction_flags"], "00000000")
		self.assertEqual(model["seller"]["endpoint"], "1234567890")
		self.assertEqual(model["buyer"]["address"]["subdivision"], "AUH")

		first, second = model["lines"]
		self.assertEqual((first["category_code"], first["rate"], first["vat_amount"]), ("S", 5, 15))
		self.assertEqual(
			(first["hs_code"], first["sac_code"], first["item_type_code"]), (None, "998311", "S")
		)
		self.assertEqual((second["category_code"], second["exemption_reason_code"]), ("E", "DL8.46.1"))
		self.assertIsNone(second["vat_amount_aed"])
		self.assertEqual({entry["code"] for entry in model["breakdown"]}, {"S", "E"})

		xml = etree.fromstring(xml_bytes)
		self.assertEqual(
			_text(xml, "cac:LegalMonetaryTotal/cbc:PayableAmount"), f"{model['totals']['payable']:.2f}"
		)

	def test_a_credit_note_model_refers_to_the_original(self):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		from uae_compliance.uae_compliance.einvoice.pint_ae_builder import build_document

		original = self.invoice(submit=True)
		credit = make_return_doc("Sales Invoice", original.name)
		credit.uae_emirate = "Dubai"
		credit.uae_credit_note_reason = "Returned"
		credit.uae_credit_note_reason_code = "DL8.61.1.D"
		credit.items[0].qty = -1
		credit.insert()

		model = build_document(credit)[2]

		self.assertEqual(model["type_code"], "381")
		self.assertEqual(model["credit_note"]["reason_code"], "DL8.61.1.D")
		self.assertEqual(model["credit_note"]["preceding_number"], original.name)
		self.assertIsNone(model["payment_means_code"])

		# ERPNext holds a return as negatives; a PINT AE credit note carries positive figures.
		self.assertEqual(model["lines"][0]["quantity"], 1)
		self.assertGreater(model["lines"][0]["net_amount"], 0)
		self.assertGreater(model["totals"]["payable"], 0)
		self.assertGreater(model["totals"]["tax_total"], 0)


class TestWhatTheInvoiceMustCarry(EInvoiceTestCase):
	def test_a_charge_outside_the_item_rows_is_refused(self):
		freight = frappe.db.get_value(
			"Account",
			{"company": self.company, "account_type": "Tax", "is_group": 0, "name": ["!=", self.output]},
			"name",
		)
		doc = self.invoice(
			taxes=[
				{"charge_type": "On Net Total", "account_head": self.output, "description": "VAT", "rate": 5},
				{
					"charge_type": "Actual",
					"account_head": freight,
					"description": "Freight",
					"tax_amount": 20,
				},
			]
		)

		with self.assertRaises(EInvoiceNotSupportedError) as ctx:
			build_xml(doc)
		self.assertIn("differs from its item rows", str(ctx.exception))

	def test_a_standard_rated_row_at_zero_percent_is_refused_not_charged_five(self):
		doc = self.invoice([{"item_code": "_Test EInv Service", "rate": 100, "vat_rate": 0}])

		with self.assertRaises(EInvoiceNotSupportedError) as ctx:
			build_xml(doc)
		self.assertIn("0% VAT rate", str(ctx.exception))

	def test_a_row_the_invoice_does_not_tax_explicitly_gets_the_standard_rate(self):
		_xml, _bytes, summary = self.build(self.invoice())
		self.assertEqual(summary["tax_total"], 100)

	def test_rounding_up_to_a_whole_dirham_is_carried(self):
		doc = self.invoice([{"item_code": "_Test EInv Service", "rate": 99.5}])
		_xml, _bytes, summary = self.build(doc)

		self.assertEqual(summary["payable"], flt_(doc.rounded_total))
		self.assertEqual(validate_xml(_bytes), [])


def flt_(value):
	return frappe.utils.flt(value, 2)


class TestNumberFormatting(FrappeTestCase):
	def test_decimals_are_fixed_point_and_keep_their_precision(self):
		from uae_compliance.uae_compliance.einvoice.pint_ae_builder import _decimal

		self.assertEqual(_decimal(123456.7, 6), "123456.7")
		self.assertEqual(_decimal(10000000, 6), "10000000")
		self.assertEqual(_decimal(3.672519, 6), "3.672519")
		self.assertEqual(_decimal(0.0000004, 6), "0")
		self.assertEqual(_decimal(5, 2), "5")
		self.assertEqual(_decimal(2.5, 2), "2.5")
		self.assertNotIn("e", _decimal(1e9, 6))

	def test_the_exchange_rate_is_written_with_its_six_decimals_and_used_for_the_aed_figures(self):
		class Doc(frappe._dict):
			pass

		from uae_compliance.uae_compliance.einvoice.pint_ae_builder import PintAEBuilder

		builder = PintAEBuilder(
			Doc(company=get_uae_test_company(), currency="USD", conversion_rate=3.6725189, items=[])
		)
		self.assertEqual(builder.rate, 3.672519)


class TestCreditNote(EInvoiceTestCase):
	def test_credit_note_structure(self):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		original = self.invoice(submit=True)
		credit = make_return_doc("Sales Invoice", original.name)
		credit.uae_emirate = "Dubai"
		credit.uae_credit_note_reason = "Goods returned"
		credit.uae_credit_note_reason_code = "DL8.61.1.D"
		credit.items[0].qty = -1
		credit.insert()

		xml, _bytes, summary = self.build(credit)

		self.assertEqual(xml.tag, "{urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2}CreditNote")
		self.assertEqual(_text(xml, "cbc:CreditNoteTypeCode"), "381")
		self.assertEqual(_text(xml, "cac:DiscrepancyResponse/cbc:ResponseCode"), "DL8.61.1.D")
		self.assertEqual(
			_text(xml, "cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID"), original.name
		)
		self.assertEqual(_find(xml, "cac:PaymentMeans"), [])
		self.assertEqual(_find(xml, "cbc:DueDate"), [])
		self.assertEqual(len(_find(xml, "cac:CreditNoteLine")), 1)
		self.assertEqual(summary["type_code"], "381")


class TestForeignCurrency(EInvoiceTestCase):
	def test_aed_figures_and_exchange_rate(self):
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
		xml, _bytes, summary = self.build(doc)

		self.assertEqual(_text(xml, "cbc:DocumentCurrencyCode"), "USD")
		self.assertEqual(_text(xml, "cbc:TaxCurrencyCode"), "AED")
		self.assertEqual(_text(xml, "cac:TaxExchangeRate/cbc:CalculationRate"), "3.6725")

		aed_total = _find(xml, "cac:TaxTotal/cbc:TaxAmount[@currencyID='AED']")
		self.assertEqual(aed_total[0].text, "367.25")  # 100 USD x 3.6725
		reference = "cac:AdditionalDocumentReference[cbc:DocumentTypeCode='aedtotal-incl-vat']/cbc:DocumentDescription"
		self.assertEqual(_text(xml, reference), "AED 7712.25")
		self.assertEqual(summary["inclusive_total"], 2100)

		self.assertEqual(validate_xml(_bytes), [])


class TestValidators(EInvoiceTestCase):
	def test_a_complete_invoice_passes(self):
		xml_bytes, _summary = build_xml(self.invoice())
		self.assertEqual(validate_xml(xml_bytes), [])

	def test_zero_rated_and_exempt_pass(self):
		doc = self.invoice(
			[
				{"item_code": "_Test EInv Service", "rate": 100},
				{"item_code": "_Test EInv Zero", "rate": 200, "vat_rate": 0},
				{"item_code": "_Test EInv Exempt", "rate": 300, "vat_rate": 0},
			]
		)
		self.assertEqual(validate_xml(build_xml(doc)[0]), [])

	def _problems(self, mutate) -> list[str]:
		xml = etree.fromstring(build_xml(self.invoice())[0])
		mutate(xml)
		return validate_xml(etree.tostring(xml))

	def test_a_foreign_buyer_needs_no_trn_or_emirate(self):
		from uae_compliance.tests import make_address

		abroad = make_address("_Test Foreign Buyer", "India", customer="_Test UAE Customer")
		frappe.db.set_value("Customer", "_Test UAE Customer", {"uae_tin": "", "uae_trn": ""})
		doc = self.invoice(
			[{"item_code": "_Test EInv Zero", "rate": 500, "vat_rate": 0}],
			customer_address=abroad.name,
			shipping_address_name=abroad.name,
		)

		self.assertEqual(validate_xml(build_xml(doc)[0]), [])

	def test_a_domestic_buyer_needs_an_emirate(self):
		def mutate(xml):
			subdivision = _find(
				xml, "cac:AccountingCustomerParty/cac:Party/cac:PostalAddress/cbc:CountrySubentity"
			)[0]
			subdivision.getparent().remove(subdivision)

		self.assertIn("no emirate", " ".join(self._problems(mutate)))

	def test_only_the_predefined_endpoints_skip_the_tin_check(self):
		def garbage(xml):
			_find(xml, "cac:AccountingCustomerParty/cac:Party/cbc:EndpointID")[0].text = "99garbage"

		self.assertIn("TIN 99garbage", " ".join(self._problems(garbage)))

		def predefined(xml):
			_find(xml, "cac:AccountingCustomerParty/cac:Party/cbc:EndpointID")[0].text = "9900000098"

		self.assertNotIn("TIN", " ".join(self._problems(predefined)))

		def seller(xml):
			_find(xml, "cac:AccountingSupplierParty/cac:Party/cbc:EndpointID")[0].text = "9900000098"

		self.assertIn("seller TIN", " ".join(self._problems(seller)))

	def test_totals_are_tied_back_to_the_lines(self):
		def mutate(xml):
			_find(xml, "cac:TaxTotal/cac:TaxSubtotal/cbc:TaxableAmount")[0].text = "4000.00"
			_find(xml, "cac:TaxTotal/cac:TaxSubtotal/cbc:TaxAmount")[0].text = "200.00"
			_find(xml, "cac:TaxTotal/cbc:TaxAmount")[0].text = "200.00"
			_find(xml, "cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount")[0].text = "2200.00"
			_find(xml, "cac:LegalMonetaryTotal/cbc:PayableAmount")[0].text = "2200.00"

		self.assertIn("not the sum of its lines", " ".join(self._problems(mutate)))

	def test_the_exclusive_total_must_match_the_lines(self):
		def mutate(xml):
			_find(xml, "cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount")[0].text = "1500.00"

		self.assertIn("excluding VAT is not the sum", " ".join(self._problems(mutate)))

	def test_a_line_must_carry_the_vat_of_its_category(self):
		def mutate(xml):
			_find(xml, "cac:InvoiceLine/cac:ItemPriceExtension/cac:TaxTotal/cbc:TaxAmount")[0].text = "1.00"

		self.assertIn("AED line amount or VAT amount does not match", " ".join(self._problems(mutate)))

	def test_a_foreign_line_with_a_rounded_vat_still_passes(self):
		"""1.09 at 5% VAT is 0.05 in USD (rounded) and 0.60 at a rate of 12, not 0.654."""
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

		doc = self.invoice(
			[{"item_code": "_Test EInv Service", "rate": 1.09}],
			currency="USD",
			conversion_rate=12,
			debit_to=account,
		)
		xml_bytes = build_xml(doc)[0]

		self.assertEqual(validate_xml(xml_bytes), [])

	def test_aed_figures_follow_the_exchange_rate(self):
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

		doc = self.invoice(currency="USD", conversion_rate=3.6725, debit_to=account)
		xml = etree.fromstring(build_xml(doc)[0])
		_find(xml, "cac:TaxTotal/cbc:TaxAmount[@currencyID='AED']")[0].text = "1.00"
		_find(xml, "cac:AdditionalDocumentReference/cbc:DocumentDescription")[0].text = "AED 5.00"

		problems = " ".join(validate_xml(etree.tostring(xml)))
		self.assertIn("total VAT in AED does not match", problems)
		self.assertIn("including VAT in AED does not match", problems)

	def test_not_well_formed(self):
		self.assertTrue(validate_xml(b"<Invoice"))

	def test_bad_trn_and_tin(self):
		def mutate(xml):
			_find(xml, "cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID")[
				0
			].text = "200123456789003"
			_find(xml, "cac:AccountingSupplierParty/cac:Party/cbc:EndpointID")[0].text = "2234567890"

		problems = " ".join(self._problems(mutate))
		self.assertIn("TRN 200123456789003", problems)
		self.assertIn("TIN 2234567890", problems)

	def test_missing_legal_registration_and_address(self):
		def mutate(xml):
			party = _find(xml, "cac:AccountingCustomerParty/cac:Party")[0]
			legal_id = _find(party, "cac:PartyLegalEntity/cbc:CompanyID")[0]
			legal_id.getparent().remove(legal_id)
			city = _find(party, "cac:PostalAddress/cbc:CityName")[0]
			city.getparent().remove(city)

		problems = " ".join(self._problems(mutate))
		self.assertIn("legal registration identifier", problems)
		self.assertIn("city", problems)

	def test_wrong_emirate_code(self):
		def mutate(xml):
			_find(xml, "cac:AccountingSupplierParty/cac:Party/cac:PostalAddress/cbc:CountrySubentity")[
				0
			].text = "XXX"

		self.assertIn("emirate code XXX", " ".join(self._problems(mutate)))

	def test_arithmetic_is_checked(self):
		def mutate(xml):
			_find(xml, "cac:LegalMonetaryTotal/cbc:PayableAmount")[0].text = "9999.00"
			_find(xml, "cac:InvoiceLine/cbc:LineExtensionAmount")[0].text = "1.00"

		problems = " ".join(self._problems(mutate))
		self.assertIn("quantity times net price", problems)
		self.assertIn("amount payable", problems)

	def test_exempt_line_needs_a_reason(self):
		xml = etree.fromstring(
			build_xml(self.invoice([{"item_code": "_Test EInv Exempt", "rate": 300, "vat_rate": 0}]))[0]
		)
		for node in _find(xml, "//cbc:TaxExemptionReasonCode"):
			node.getparent().remove(node)

		self.assertIn("exemption reason", " ".join(validate_xml(etree.tostring(xml))))

	def test_goods_need_an_hs_code(self):
		from uae_compliance.tests import make_einvoice_item

		make_einvoice_item("_Test EInv Goods2", uae_item_type="Goods")
		doc = self.invoice([{"item_code": "_Test EInv Goods2", "rate": 100}])
		self.assertIn("HS code", " ".join(validate_xml(build_xml(doc)[0])))

	def test_credit_note_needs_a_reason_code(self):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		original = self.invoice(submit=True)
		credit = make_return_doc("Sales Invoice", original.name)
		credit.uae_emirate = "Dubai"
		credit.uae_credit_note_reason = "Returned"
		credit.items[0].qty = -1
		credit.insert()

		self.assertIn("reason code", " ".join(validate_xml(build_xml(credit)[0])))

	def test_raise_if_invalid(self):
		xml = etree.fromstring(build_xml(self.invoice())[0])
		_find(xml, "cbc:UUID")[0].text = ""
		with self.assertRaises(EInvoiceError):
			raise_if_invalid(etree.tostring(xml))

		raise_if_invalid(build_xml(self.invoice())[0])


class TestAgainstTheUBLSchema(EInvoiceTestCase):
	def setUp(self):
		super().setUp()
		if not UBL_XSD_DIR or not Path(UBL_XSD_DIR, "maindoc", "UBL-Invoice-2.1.xsd").exists():
			self.skipTest("UBL_XSD_DIR is not set")

	def _schema(self, name):
		return etree.XMLSchema(etree.parse(str(Path(UBL_XSD_DIR, "maindoc", f"UBL-{name}-2.1.xsd"))))

	def test_invoice_is_valid_ubl(self):
		doc = self.invoice(
			[
				{"item_code": "_Test EInv Service", "rate": 100},
				{"item_code": "_Test EInv Zero", "rate": 200, "vat_rate": 0},
				{"item_code": "_Test EInv Exempt", "rate": 300, "vat_rate": 0},
			]
		)
		schema = self._schema("Invoice")
		schema.assertValid(etree.fromstring(build_xml(doc)[0]))

	def test_credit_note_is_valid_ubl(self):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		original = self.invoice(submit=True)
		credit = make_return_doc("Sales Invoice", original.name)
		credit.uae_emirate = "Dubai"
		credit.uae_credit_note_reason = "Returned"
		credit.uae_credit_note_reason_code = "DL8.61.1.D"
		credit.items[0].qty = -1
		credit.insert()

		self._schema("CreditNote").assertValid(etree.fromstring(build_xml(credit)[0]))


PINT_RULES_DIR = os.environ.get("PINT_AE_RESOURCES_DIR")


class TestAgainstTheOfficialSchematron(EInvoiceTestCase):
	"""Runs the official PINT AE rules (the preprocessed Schematron stylesheets from the specification's
	resources.zip) with Saxon. Needs `saxonche` and PINT_AE_RESOURCES_DIR, the unpacked resources
	folder; skipped otherwise."""

	def setUp(self):
		super().setUp()
		try:
			import saxonche
		except ImportError:
			self.skipTest("saxonche is not installed")

		if not PINT_RULES_DIR or not Path(PINT_RULES_DIR, "trn-invoice").exists():
			self.skipTest("PINT_AE_RESOURCES_DIR is not set")

	def _failures(self, xml_bytes: bytes, folder: str) -> list[str]:
		import re
		import tempfile

		from saxonche import PySaxonProcessor

		failures = []
		with (
			PySaxonProcessor(license=False) as processor,
			tempfile.NamedTemporaryFile(suffix=".xml") as source,
		):
			source.write(xml_bytes)
			source.flush()
			xslt = processor.new_xslt30_processor()
			for sheet in ("PINT-UBL-validation-preprocessed.xslt", "PINT-jurisdiction-aligned-rules.xslt"):
				executable = xslt.compile_stylesheet(
					stylesheet_file=str(Path(PINT_RULES_DIR, folder, "schematron", sheet))
				)
				output = executable.transform_to_string(source_file=source.name) or ""
				for match in re.finditer(
					r"<svrl:failed-assert([^>]*)>.*?<svrl:text>(.*?)</svrl:text>", output, re.S
				):
					rule = re.search(r'id="([^"]+)"', match.group(1))
					failures.append(
						f"{rule.group(1) if rule else '?'}: {' '.join(match.group(2).split())[:160]}"
					)

		return failures

	def test_invoice_has_no_failed_rules(self):
		doc = self.invoice(
			[
				{"item_code": "_Test EInv Service", "rate": 100, "qty": 3},
				{"item_code": "_Test EInv Zero", "rate": 200, "vat_rate": 0},
				{"item_code": "_Test EInv Exempt", "rate": 300, "vat_rate": 0},
			]
		)
		self.assertEqual(self._failures(build_xml(doc)[0], "trn-invoice"), [])

	def test_credit_note_has_no_failed_rules(self):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		original = self.invoice(submit=True)
		credit = make_return_doc("Sales Invoice", original.name)
		credit.uae_emirate = "Dubai"
		credit.uae_credit_note_reason = "Returned"
		credit.uae_credit_note_reason_code = "DL8.61.1.D"
		credit.items[0].qty = -1
		credit.insert()

		self.assertEqual(self._failures(build_xml(credit)[0], "trn-creditnote"), [])

	def test_foreign_currency_invoice_has_no_failed_rules(self):
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

		doc = self.invoice(currency="USD", conversion_rate=3.6725, debit_to=account)
		self.assertEqual(self._failures(build_xml(doc)[0], "trn-invoice"), [])

	def test_the_rules_do_catch_a_broken_document(self):
		xml = build_xml(self.invoice())[0].replace(b"UUID", b"XUUID")
		self.assertIn("ibr-193-ae", " ".join(self._failures(xml, "trn-invoice")))
