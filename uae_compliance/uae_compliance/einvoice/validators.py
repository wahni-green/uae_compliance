"""Checks an e-invoice before it is sent, so a rejection by the network is caught early.

These are the arithmetic, identifier and conditional-presence rules of the PINT AE Schematron that
matter for the invoices this app builds, written in Python. They are not the full Schematron: that
needs an XSLT 2 processor. Validate against the official files too before going live (see
docs/UAE_COMPLIANCE_ARCHITECTURE.md)."""

import re

import frappe
from frappe import _
from frappe.utils import flt
from lxml import etree

from uae_compliance.uae_compliance.constants.pint_ae import (
	CREDIT_NOTE_TYPE_CODE,
	CREDIT_REASONS,
	CUSTOMIZATION_ID,
	EMIRATE_SUBDIVISIONS,
	ENDPOINT_BUYER_NOT_ON_NETWORK,
	ENDPOINT_EXPORT,
	INVOICE_TYPE_CODE,
	PINT_TIN_PATTERN,
	PINT_TRN_PATTERN,
	PROFILE_ID,
)
from uae_compliance.uae_compliance.einvoice.pint_ae_builder import NAMESPACES, ROOTS

TOLERANCE = 0.011
# AED figures are the document figures times the exchange rate, each rounded to the cent.
AED_TOLERANCE = 0.05


def _x(xml: etree._Element, path: str):
	return xml.xpath(
		path,
		namespaces={
			"cac": NAMESPACES["cac"],
			"cbc": NAMESPACES["cbc"],
			"i": ROOTS["Invoice"],
			"n": ROOTS["CreditNote"],
		},
	)


def _text(xml, path: str) -> str:
	found = _x(xml, path)
	return (found[0].text or "").strip() if found else ""


def validate_xml(xml_bytes: bytes) -> list[str]:
	"""The problems found in a PINT AE document, empty when it passes."""
	try:
		xml = etree.fromstring(xml_bytes)
	except etree.XMLSyntaxError as e:
		return [_("The XML is not well formed: {0}").format(str(e))]

	is_credit_note = xml.tag == f"{{{ROOTS['CreditNote']}}}CreditNote"
	line_tag = "CreditNoteLine" if is_credit_note else "InvoiceLine"
	errors: list[str] = []

	errors += _check_header(xml, is_credit_note)
	errors += _check_parties(xml)
	errors += _check_lines(xml, line_tag, is_credit_note)
	errors += _check_totals(xml, line_tag)
	errors += _check_currency(xml)
	errors += _check_conditional(xml, is_credit_note, line_tag)

	return errors


def _check_header(xml, is_credit_note: bool) -> list[str]:
	errors = []
	if _text(xml, "cbc:CustomizationID") != CUSTOMIZATION_ID:
		errors.append(_("The specification identifier must be {0}.").format(CUSTOMIZATION_ID))
	if _text(xml, "cbc:ProfileID") != PROFILE_ID:
		errors.append(_("The business process must be {0}.").format(PROFILE_ID))
	if not re.fullmatch(r"[01]{8}", _text(xml, "cbc:ProfileExecutionID")):
		errors.append(_("The transaction type must be eight characters of 0 and 1."))
	for tag, label in (
		("ID", _("invoice number")),
		("UUID", _("unique identifier")),
		("IssueDate", _("issue date")),
	):
		if not _text(xml, f"cbc:{tag}"):
			errors.append(_("The {0} is missing.").format(label))

	type_tag = "CreditNoteTypeCode" if is_credit_note else "InvoiceTypeCode"
	expected = CREDIT_NOTE_TYPE_CODE if is_credit_note else INVOICE_TYPE_CODE
	if _text(xml, f"cbc:{type_tag}") != expected:
		errors.append(_("The document type code must be {0}.").format(expected))

	if not re.fullmatch(r"[A-Z]{3}", _text(xml, "cbc:DocumentCurrencyCode")):
		errors.append(_("The document currency is missing or not a currency code."))

	return errors


PREDEFINED_BUYER_ENDPOINTS = (ENDPOINT_BUYER_NOT_ON_NETWORK, ENDPOINT_EXPORT, "9900000097")


def _check_parties(xml) -> list[str]:
	errors = []
	for role, label in (("AccountingSupplierParty", _("seller")), ("AccountingCustomerParty", _("buyer"))):
		base = f"cac:{role}/cac:Party"
		is_buyer = role == "AccountingCustomerParty"
		country = _text(xml, f"{base}/cac:PostalAddress/cac:Country/cbc:IdentificationCode")
		is_domestic = country in ("", "AE")
		endpoint = _text(xml, f"{base}/cbc:EndpointID")
		predefined = is_buyer and endpoint in PREDEFINED_BUYER_ENDPOINTS

		# The seller always has a TIN. A buyer has one too, or one of the predefined endpoints for a
		# buyer that is not on the network or is abroad.
		if not endpoint:
			errors.append(_("The {0} has no Peppol endpoint (TIN).").format(label))
		elif not predefined and not re.fullmatch(PINT_TIN_PATTERN, endpoint):
			errors.append(_("The {0} TIN {1} must be 10 digits, starting with 1.").format(label, endpoint))

		trn = _text(xml, f"{base}/cac:PartyTaxScheme/cbc:CompanyID")
		legal_id = _text(xml, f"{base}/cac:PartyLegalEntity/cbc:CompanyID")
		if trn and not re.fullmatch(PINT_TRN_PATTERN, trn):
			errors.append(
				_("The {0} TRN {1} must be 15 digits, starting with 1 and ending with 03.").format(label, trn)
			)
		# A seller always has a TRN. A domestic buyer has a TRN or at least a legal registration; a
		# buyer abroad has neither to give.
		if not trn and (not is_buyer or (is_domestic and not legal_id)):
			errors.append(_("The {0} has no VAT registration number (TRN).").format(label))

		if not _text(xml, f"{base}/cac:PartyLegalEntity/cbc:RegistrationName"):
			errors.append(_("The {0} has no legal name.").format(label))

		if not legal_id and (not is_buyer or (is_domestic and not predefined)):
			errors.append(_("The {0} has no legal registration identifier.").format(label))

		legal_entity = _x(xml, f"{base}/cac:PartyLegalEntity/cbc:CompanyID")
		if legal_entity and legal_entity[0].get("schemeAgencyID") == "PAS":
			if not re.fullmatch(r"[A-Z]{2}", legal_entity[0].get("schemeAgencyName") or ""):
				errors.append(_("The {0} passport needs the country that issued it.").format(label))

		for tag, what in (("StreetName", _("address line")), ("CityName", _("city"))):
			if not _text(xml, f"{base}/cac:PostalAddress/cbc:{tag}"):
				errors.append(_("The {0} has no {1}.").format(label, what))

		subdivision = _text(xml, f"{base}/cac:PostalAddress/cbc:CountrySubentity")
		if is_domestic:
			if not subdivision:
				errors.append(_("The {0} has no emirate.").format(label))
			elif subdivision not in EMIRATE_SUBDIVISIONS.values():
				errors.append(
					_("The {0} emirate code {1} is not one of {2}.").format(
						label, subdivision, ", ".join(EMIRATE_SUBDIVISIONS.values())
					)
				)

	return errors


def _check_lines(xml, line_tag: str, is_credit_note: bool) -> list[str]:
	errors = []
	lines = _x(xml, f"cac:{line_tag}")
	if not lines:
		return [_("The document has no lines.")]

	quantity_tag = "CreditedQuantity" if is_credit_note else "InvoicedQuantity"
	rate_to_aed = flt(_text(xml, "cac:TaxExchangeRate/cbc:CalculationRate")) or 1
	for line in lines:
		number = _text(line, "cbc:ID")
		quantity = flt(_text(line, f"cbc:{quantity_tag}"))
		net = flt(_text(line, "cbc:LineExtensionAmount"))
		price = flt(_text(line, "cac:Price/cbc:PriceAmount"))
		base = flt(_text(line, "cac:Price/cbc:BaseQuantity")) or 1

		if abs(net - quantity * price / base) > TOLERANCE:
			errors.append(
				_("Line {0}: the line amount {1} is not quantity times net price.").format(number, net)
			)

		category = _text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID")
		rate = _text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent")
		if not category:
			errors.append(_("Line {0}: the VAT category is missing.").format(number))
		if category == "Z" and flt(rate):
			errors.append(_("Line {0}: a zero rated line must have a 0% rate.").format(number))
		if category == "E" and not _text(
			line, "cac:Item/cac:ClassifiedTaxCategory/cbc:TaxExemptionReasonCode"
		):
			errors.append(_("Line {0}: an exempt line needs a VAT exemption reason code.").format(number))
		if category == "S" and not flt(rate):
			errors.append(_("Line {0}: a standard rated line needs a rate above 0%.").format(number))

		if not _text(line, "cac:Item/cbc:Name") or not _text(line, "cac:Item/cbc:Description"):
			errors.append(_("Line {0}: the item name and description are required.").format(number))

		item_type = _text(line, "cac:Item/cac:CommodityClassification/cbc:CommodityCode")
		hs_codes = _x(line, "cac:Item/cac:CommodityClassification/cbc:ItemClassificationCode[@listID='HS']")
		sac_codes = _x(line, "cac:Item/cac:AdditionalItemIdentification/cbc:ID[@schemeID='SAC']")
		if item_type in ("G", "B") and not hs_codes:
			errors.append(
				_("Line {0}: goods need an HS code (customs tariff number on the Item).").format(number)
			)
		if item_type in ("S", "B") and not sac_codes:
			errors.append(_("Line {0}: services need a service accounting code on the Item.").format(number))

		if category != "E":
			extension_tax = _text(line, "cac:ItemPriceExtension/cac:TaxTotal/cbc:TaxAmount")
			extension_amount = _text(line, "cac:ItemPriceExtension/cbc:Amount")
			if not extension_tax or not extension_amount:
				errors.append(_("Line {0}: the AED line amount and VAT amount are required.").format(number))
			else:
				# The builder rounds the VAT in the document currency before converting it.
				vat = flt(net * flt(rate) / 100, 2)
				if (
					abs(flt(extension_tax) - vat * rate_to_aed) > AED_TOLERANCE
					or abs(flt(extension_amount) - (net + vat) * rate_to_aed) > AED_TOLERANCE
				):
					errors.append(
						_("Line {0}: the AED line amount or VAT amount does not match the line.").format(
							number
						)
					)
		elif _x(line, "cac:ItemPriceExtension/cac:TaxTotal/cbc:TaxAmount"):
			errors.append(_("Line {0}: an exempt line must not carry a VAT amount.").format(number))

	return errors


def _check_totals(xml, line_tag: str) -> list[str]:
	errors = []
	lines = _x(xml, f"cac:{line_tag}")
	lines_total = sum(flt(_text(line, "cbc:LineExtensionAmount")) for line in lines)
	monetary = "cac:LegalMonetaryTotal/cbc:"
	if abs(flt(_text(xml, monetary + "LineExtensionAmount")) - lines_total) > TOLERANCE:
		errors.append(_("The sum of the line amounts does not match the invoice total."))

	exclusive = flt(_text(xml, monetary + "TaxExclusiveAmount"))
	if abs(exclusive - lines_total) > TOLERANCE:
		errors.append(_("The total excluding VAT is not the sum of the line amounts."))

	# Each VAT breakdown is the sum of the lines under its category and rate.
	by_category: dict[tuple[str, float], float] = {}
	for line in lines:
		key = (
			_text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID"),
			flt(_text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent")),
		)
		by_category[key] = by_category.get(key, 0) + flt(_text(line, "cbc:LineExtensionAmount"))

	subtotals = _x(xml, "cac:TaxTotal[cac:TaxSubtotal]/cac:TaxSubtotal")
	tax_total = flt(_text(xml, "cac:TaxTotal[cac:TaxSubtotal]/cbc:TaxAmount"))
	if abs(sum(flt(_text(s, "cbc:TaxAmount")) for s in subtotals) - tax_total) > TOLERANCE:
		errors.append(_("The VAT breakdown does not add up to the total VAT."))

	seen = set()
	for subtotal in subtotals:
		key = (
			_text(subtotal, "cac:TaxCategory/cbc:ID"),
			flt(_text(subtotal, "cac:TaxCategory/cbc:Percent")),
		)
		seen.add(key)
		taxable = flt(_text(subtotal, "cbc:TaxableAmount"))
		tax = flt(_text(subtotal, "cbc:TaxAmount"))
		if abs(taxable - by_category.get(key, 0)) > TOLERANCE:
			errors.append(_("The taxable amount of category {0} is not the sum of its lines.").format(key[0]))
		if abs(tax - taxable * key[1] / 100) > TOLERANCE:
			errors.append(_("A VAT breakdown amount does not equal its taxable amount times its rate."))

	if seen != set(by_category):
		errors.append(_("The VAT breakdown does not cover the categories of the lines."))

	inclusive = flt(_text(xml, monetary + "TaxInclusiveAmount"))
	if abs(exclusive + tax_total - inclusive) > TOLERANCE:
		errors.append(_("The total including VAT is not the total excluding VAT plus the VAT."))

	payable = flt(_text(xml, monetary + "PayableAmount"))
	rounding = flt(_text(xml, monetary + "PayableRoundingAmount"))
	if abs(inclusive + rounding - payable) > TOLERANCE:
		errors.append(_("The amount payable is not the total including VAT plus the rounding."))

	return errors


def _check_currency(xml) -> list[str]:
	errors = []
	currency = _text(xml, "cbc:DocumentCurrencyCode")
	if currency == "AED":
		return errors

	if _text(xml, "cbc:TaxCurrencyCode") != "AED":
		errors.append(_("A document in {0} needs the tax currency AED.").format(currency))
	exchange = "cac:TaxExchangeRate"
	if not (
		_text(xml, f"{exchange}/cbc:SourceCurrencyCode") == currency
		and _text(xml, f"{exchange}/cbc:TargetCurrencyCode") == "AED"
		and flt(_text(xml, f"{exchange}/cbc:CalculationRate"))
	):
		errors.append(_("A document in {0} needs the exchange rate to AED.").format(currency))
	rate_text = _text(xml, f"{exchange}/cbc:CalculationRate")
	if "." in rate_text and len(rate_text.split(".")[1]) > 6:
		errors.append(_("The exchange rate can have at most six decimals."))
	rate = flt(rate_text)
	aed_tax = _x(xml, "cac:TaxTotal/cbc:TaxAmount[@currencyID='AED']")
	if not aed_tax:
		errors.append(_("The total VAT in AED is required."))
	else:
		tax_total = flt(_text(xml, "cac:TaxTotal[cac:TaxSubtotal]/cbc:TaxAmount"))
		if abs(flt(aed_tax[0].text) - tax_total * rate) > AED_TOLERANCE:
			errors.append(_("The total VAT in AED does not match the VAT times the exchange rate."))

	description = _text(
		xml,
		"cac:AdditionalDocumentReference[cbc:DocumentTypeCode='aedtotal-incl-vat']/cbc:DocumentDescription",
	)
	if not description:
		errors.append(_("The total including VAT in AED is required."))
	else:
		inclusive = flt(_text(xml, "cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount"))
		if abs(flt(description.replace("AED", "").strip()) - inclusive * rate) > AED_TOLERANCE:
			errors.append(
				_("The total including VAT in AED does not match the total times the exchange rate.")
			)

	return errors


def _check_conditional(xml, is_credit_note: bool, line_tag: str) -> list[str]:
	errors = []
	if is_credit_note:
		if not _x(xml, "cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID"):
			errors.append(_("A credit note must refer to the invoice it credits."))
		reason = _text(xml, "cac:DiscrepancyResponse/cbc:ResponseCode")
		if reason not in CREDIT_REASONS:
			errors.append(
				_("A credit note needs a reason code from the list ({0}).").format(", ".join(CREDIT_REASONS))
			)
	else:
		payable = flt(_text(xml, "cac:LegalMonetaryTotal/cbc:PayableAmount"))
		if payable > 0 and not _text(xml, "cbc:DueDate"):
			errors.append(_("An invoice with an amount due needs a due date."))
		if not _x(xml, "cac:PaymentMeans/cbc:PaymentMeansCode"):
			errors.append(_("The payment means are required."))

	tax_point = _text(xml, "cbc:TaxPointDate")
	if tax_point and tax_point >= _text(xml, "cbc:IssueDate"):
		errors.append(_("The VAT point date must be before the issue date."))

	return errors


def raise_if_invalid(xml_bytes: bytes) -> None:
	errors = validate_xml(xml_bytes)
	if errors:
		from uae_compliance.uae_compliance.einvoice.exceptions import EInvoiceError

		frappe.throw("<br>".join(errors), exc=EInvoiceError, title=_("Invalid E-Invoice"))
