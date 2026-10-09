"""Builds the PINT AE (Peppol UAE) UBL 2.1 XML of a Sales Invoice.

Follows the samples and Schematron rules of the PINT AE specification (see docs/UAE_VERIFICATION.md,
section 4). The supported scope is the standard tax invoice (380) and tax credit note (381) for
standard rated, zero rated and exempt supplies, including exports and the margin scheme flags, in AED
or in a foreign currency with the AED figures. Reverse charge supplies, out of scope supplies,
summary, continuous, agent billing and deemed supplies are refused with a clear message.
"""

import uuid

import frappe
from frappe import _
from frappe.utils import flt, get_time, getdate
from lxml import etree

from uae_compliance.uae_compliance.constants import STANDARD_VAT_RATE
from uae_compliance.uae_compliance.constants.pint_ae import (
	CATEGORY_CODES,
	CREDIT_NOTE_TYPE_CODE,
	CUSTOMIZATION_ID,
	DEFAULT_UNIT_CODE,
	EMIRATE_SUBDIVISIONS,
	ENDPOINT_BUYER_NOT_ON_NETWORK,
	ENDPOINT_EXPORT,
	ENDPOINT_SCHEME,
	FLAG_EXPORT,
	FLAG_MARGIN_SCHEME,
	INVOICE_TYPE_CODE,
	ITEM_TYPE_CODES,
	LEGAL_REGISTRATION_TYPES,
	PAYMENT_MEANS_CODE,
	PROFILE_ID,
	TRADE_LICENSE_AGENCY,
	UNIT_CODES,
	UTC_OFFSET,
)
from uae_compliance.uae_compliance.einvoice.exceptions import EInvoiceNotSupportedError
from uae_compliance.uae_compliance.utils.tax_account import (
	get_item_wise_vat_rates,
	is_output_vat_account,
)
from uae_compliance.uae_compliance.utils.vat_return import CategoryResolver

NAMESPACES = {
	"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
	"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}
ROOTS = {
	"Invoice": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
	"CreditNote": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2",
}


def build_xml(doc) -> tuple[bytes, dict]:
	"""The PINT AE XML of a Sales Invoice (or return) and a summary of what it reports."""
	return PintAEBuilder(doc).build()


def _q(prefix: str, tag: str) -> str:
	return f"{{{NAMESPACES[prefix]}}}{tag}"


def _add(parent, prefix: str, tag: str, text=None, **attributes):
	element = etree.SubElement(parent, _q(prefix, tag), **attributes)
	if text is not None:
		element.text = str(text)

	return element


def _amount(value) -> str:
	return f"{flt(value, 2):.2f}"


def _price(value) -> str:
	return f"{flt(value, 6):.6f}".rstrip("0").rstrip(".") or "0"


class PintAEBuilder:
	def __init__(self, doc):
		self.doc = doc
		self.is_credit_note = bool(doc.get("is_return"))
		self.root_name = "CreditNote" if self.is_credit_note else "Invoice"
		self.currency = doc.currency
		self.company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
		self.rate = flt(doc.get("conversion_rate")) or 1
		self.is_foreign = self.currency != "AED"
		self.lines: list[dict] = []
		self.breakdown: dict[tuple[str, float], dict] = {}

	# ------------------------------------------------------------------ assembly

	def build(self) -> tuple[bytes, dict]:
		self._refuse_unsupported()
		self._compute_lines()
		self._compute_totals()

		root = etree.Element(_q_root(self.root_name), nsmap={None: ROOTS[self.root_name], **NAMESPACES})
		self._header(root)
		self._references(root)
		self._parties(root)
		self._payment_means(root)
		self._tax_totals(root)
		self._monetary_total(root)
		for line in self.lines:
			self._line(root, line)

		xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
		return xml, self._summary()

	def _refuse_unsupported(self):
		doc = self.doc
		if self.company_currency != "AED":
			raise EInvoiceNotSupportedError(
				_("E-invoicing needs the company currency to be AED, not {0}.").format(self.company_currency)
			)

		if doc.get("uae_is_margin_scheme"):
			# The specification reports a margin scheme invoice under the "standard rate additional
			# VAT" category (rule ibr-116-ae), which this builder does not produce yet.
			raise EInvoiceNotSupportedError(
				_("Profit margin scheme invoices cannot be sent as e-invoices yet.")
			)

	def _compute_lines(self):
		resolver = CategoryResolver()
		rates = get_item_wise_vat_rates(self.doc.get("taxes") or [], self.doc.company, is_output_vat_account)

		for row in self.doc.items:
			category = resolver.resolve(row)
			code = CATEGORY_CODES.get(category)
			if not code:
				raise EInvoiceNotSupportedError(
					_("Row #{0}: {1} supplies cannot be sent as e-invoices yet.").format(row.idx, _(category))
				)

			if code == "S":
				vat_rate = flt(rates.get(row.item_code)) or STANDARD_VAT_RATE
			else:
				vat_rate = 0.0

			net = flt(row.net_amount, 2)
			vat = flt(net * vat_rate / 100, 2) if code == "S" else 0.0
			qty = flt(row.qty) or 1
			net_price = flt(net / qty, 6)
			gross_price = flt(row.get("price_list_rate") or row.rate, 6)

			self.lines.append(
				{
					"row": row,
					"code": code,
					"rate": vat_rate,
					"net": net,
					"vat": vat,
					"qty": qty,
					"net_price": net_price,
					"gross_price": max(gross_price, net_price),
					"total": flt(net + vat, 2),
					"category": category,
				}
			)

			key = (code, vat_rate)
			entry = self.breakdown.setdefault(
				key,
				{
					"code": code,
					"rate": vat_rate,
					"taxable": 0.0,
					"tax": 0.0,
					"reason": self._exemption_reason(row),
				},
			)
			entry["taxable"] += net

		for entry in self.breakdown.values():
			entry["taxable"] = flt(entry["taxable"], 2)
			entry["tax"] = flt(entry["taxable"] * entry["rate"] / 100, 2) if entry["code"] == "S" else 0.0

	def _exemption_reason(self, row) -> str | None:
		template = row.get("item_tax_template")
		code = template and frappe.db.get_value("Item Tax Template", template, "uae_exemption_reason_code")
		return code or frappe.db.get_value("Item", row.item_code, "uae_exemption_reason_code") or None

	def _compute_totals(self):
		self.line_total = flt(sum(line["net"] for line in self.lines), 2)
		self.tax_total = flt(sum(entry["tax"] for entry in self.breakdown.values()), 2)
		self.inclusive_total = flt(self.line_total + self.tax_total, 2)
		self.rounding = 0.0
		if self.doc.get("rounded_total") and not self.doc.get("disable_rounded_total"):
			self.rounding = flt(flt(self.doc.rounded_total) - self.inclusive_total, 2)
			if abs(self.rounding) >= 1:
				self.rounding = 0.0

		self.payable = flt(self.inclusive_total + self.rounding, 2)
		self.tax_total_aed = flt(self.tax_total * self.rate, 2) if self.is_foreign else self.tax_total
		self.inclusive_total_aed = (
			flt(self.inclusive_total * self.rate, 2) if self.is_foreign else self.inclusive_total
		)

	def _summary(self) -> dict:
		return {
			"uuid": self.uuid,
			"number": self.doc.name,
			"type_code": CREDIT_NOTE_TYPE_CODE if self.is_credit_note else INVOICE_TYPE_CODE,
			"currency": self.currency,
			"line_total": self.line_total,
			"tax_total": self.tax_total,
			"inclusive_total": self.inclusive_total,
			"payable": self.payable,
			"rounding": self.rounding,
			"lines": len(self.lines),
		}

	# ------------------------------------------------------------------ sections

	@property
	def uuid(self) -> str:
		if not self.doc.get("uae_einvoice_uuid"):
			self.doc.uae_einvoice_uuid = str(uuid.uuid4())

		return self.doc.uae_einvoice_uuid

	def _transaction_flags(self) -> str:
		flags = ["0"] * 8
		if self.doc.get("uae_is_margin_scheme"):
			flags[FLAG_MARGIN_SCHEME] = "1"
		if self.doc.get("uae_is_export"):
			flags[FLAG_EXPORT] = "1"

		return "".join(flags)

	def _header(self, root):
		doc = self.doc
		_add(root, "cbc", "CustomizationID", CUSTOMIZATION_ID)
		_add(root, "cbc", "ProfileID", PROFILE_ID)
		_add(root, "cbc", "ProfileExecutionID", self._transaction_flags())
		_add(root, "cbc", "ID", doc.name)
		_add(root, "cbc", "UUID", self.uuid)
		_add(root, "cbc", "IssueDate", getdate(doc.posting_date).isoformat())
		_add(
			root,
			"cbc",
			"IssueTime",
			f"{get_time(doc.get('posting_time') or '00:00:00').strftime('%H:%M:%S')}{UTC_OFFSET}",
		)
		if not self.is_credit_note and doc.get("due_date"):
			_add(root, "cbc", "DueDate", getdate(doc.due_date).isoformat())

		if self.is_credit_note:
			_add(root, "cbc", "CreditNoteTypeCode", CREDIT_NOTE_TYPE_CODE)
		else:
			_add(root, "cbc", "InvoiceTypeCode", INVOICE_TYPE_CODE)

		supply = doc.get("uae_supply_date")
		if supply and not self.is_credit_note and getdate(supply) < getdate(doc.posting_date):
			_add(root, "cbc", "TaxPointDate", getdate(supply).isoformat())

		_add(root, "cbc", "DocumentCurrencyCode", self.currency)
		if self.is_foreign:
			_add(root, "cbc", "TaxCurrencyCode", "AED")

		if doc.get("po_no"):
			_add(root, "cbc", "BuyerReference", doc.po_no)

		if self.is_credit_note:
			response = _add(root, "cac", "DiscrepancyResponse")
			_add(response, "cbc", "ResponseCode", doc.get("uae_credit_note_reason_code") or "")

	def _references(self, root):
		doc = self.doc
		if self.is_credit_note and doc.get("return_against"):
			original = frappe.db.get_value(
				"Sales Invoice", doc.return_against, ["name", "posting_date"], as_dict=True
			)
			billing = _add(root, "cac", "BillingReference")
			reference = _add(billing, "cac", "InvoiceDocumentReference")
			_add(reference, "cbc", "ID", original.name)
			_add(reference, "cbc", "IssueDate", getdate(original.posting_date).isoformat())

		if self.is_foreign:
			reference = _add(root, "cac", "AdditionalDocumentReference")
			_add(reference, "cbc", "ID", "AED")
			_add(reference, "cbc", "DocumentTypeCode", "aedtotal-incl-vat")
			_add(reference, "cbc", "DocumentDescription", f"AED {_amount(self.inclusive_total_aed)}")

	def _party(self, parent, role: str, details: dict):
		wrapper = _add(parent, "cac", role)
		party = _add(wrapper, "cac", "Party")
		_add(party, "cbc", "EndpointID", details["endpoint"], schemeID=ENDPOINT_SCHEME)

		name = _add(party, "cac", "PartyName")
		_add(name, "cbc", "Name", details["name"])

		address = details["address"]
		postal = _add(party, "cac", "PostalAddress")
		if address.get("street"):
			_add(postal, "cbc", "StreetName", address["street"])
		if address.get("city"):
			_add(postal, "cbc", "CityName", address["city"])
		if address.get("subdivision"):
			_add(postal, "cbc", "CountrySubentity", address["subdivision"])
		country = _add(postal, "cac", "Country")
		_add(country, "cbc", "IdentificationCode", address.get("country") or "AE")

		if details["trn"]:
			tax_scheme = _add(party, "cac", "PartyTaxScheme")
			_add(tax_scheme, "cbc", "CompanyID", details["trn"])
			scheme = _add(tax_scheme, "cac", "TaxScheme")
			_add(scheme, "cbc", "ID", "VAT")

		legal = _add(party, "cac", "PartyLegalEntity")
		_add(legal, "cbc", "RegistrationName", details["legal_name"])
		if details["legal_id"]:
			attributes = {}
			agency = LEGAL_REGISTRATION_TYPES.get(details["legal_type"])
			if agency:
				attributes["schemeAgencyID"] = agency
				if agency == "TL":
					attributes["schemeAgencyName"] = details["authority"] or TRADE_LICENSE_AGENCY
			_add(legal, "cbc", "CompanyID", details["legal_id"], **attributes)

	def _address(self, address_name: str | None) -> dict:
		if not address_name:
			return {}

		address = frappe.db.get_value(
			"Address",
			address_name,
			["address_line1", "city", "uae_emirate", "state", "country"],
			as_dict=True,
		)
		country = frappe.db.get_value("Country", address.country, "code") if address.country else None
		return {
			"street": address.address_line1,
			"city": address.city,
			"subdivision": EMIRATE_SUBDIVISIONS.get(address.uae_emirate) or address.state,
			"country": (country or "ae").upper(),
		}

	def _parties(self, root):
		doc = self.doc
		company = frappe.db.get_value(
			"Company",
			doc.company,
			[
				"uae_tin",
				"uae_trn",
				"uae_legal_registration_id",
				"uae_legal_registration_type",
				"uae_licence_authority",
			],
			as_dict=True,
		)
		self._party(
			root,
			"AccountingSupplierParty",
			{
				"endpoint": company.uae_tin or "",
				"name": doc.company,
				"legal_name": doc.company,
				"trn": company.uae_trn,
				"legal_id": company.uae_legal_registration_id,
				"legal_type": company.uae_legal_registration_type,
				"authority": company.uae_licence_authority,
				"address": self._address(doc.get("company_address")),
			},
		)

		customer = frappe.db.get_value(
			"Customer",
			doc.customer,
			[
				"customer_name",
				"uae_tin",
				"uae_trn",
				"uae_legal_registration_id",
				"uae_legal_registration_type",
				"uae_licence_authority",
			],
			as_dict=True,
		)
		address = self._address(doc.get("customer_address"))
		# A buyer that is not on the network yet, or abroad, uses a predefined endpoint.
		endpoint = customer.uae_tin or (
			ENDPOINT_EXPORT if address.get("country") not in (None, "AE") else ENDPOINT_BUYER_NOT_ON_NETWORK
		)
		self._party(
			root,
			"AccountingCustomerParty",
			{
				"endpoint": endpoint,
				"name": customer.customer_name,
				"legal_name": doc.customer_name or customer.customer_name,
				"trn": customer.uae_trn,
				"legal_id": customer.uae_legal_registration_id,
				"legal_type": customer.uae_legal_registration_type,
				"authority": customer.uae_licence_authority,
				"address": address,
			},
		)

	def _payment_means(self, root):
		# A credit note carries no payment means.
		if self.is_credit_note:
			return

		means = _add(root, "cac", "PaymentMeans")
		_add(means, "cbc", "PaymentMeansCode", PAYMENT_MEANS_CODE, name="Instrument Not Defined")

	def _tax_totals(self, root):
		if self.is_foreign:
			exchange = _add(root, "cac", "TaxExchangeRate")
			_add(exchange, "cbc", "SourceCurrencyCode", self.currency)
			_add(exchange, "cbc", "TargetCurrencyCode", "AED")
			_add(exchange, "cbc", "CalculationRate", f"{flt(self.rate, 6):g}")

		total = _add(root, "cac", "TaxTotal")
		_add(total, "cbc", "TaxAmount", _amount(self.tax_total), currencyID=self.currency)
		_add(total, "cbc", "TaxIncludedIndicator", "false")
		for entry in self.breakdown.values():
			subtotal = _add(total, "cac", "TaxSubtotal")
			_add(subtotal, "cbc", "TaxableAmount", _amount(entry["taxable"]), currencyID=self.currency)
			_add(subtotal, "cbc", "TaxAmount", _amount(entry["tax"]), currencyID=self.currency)
			self._tax_category(subtotal, entry["code"], entry["rate"], entry["reason"])

		if self.is_foreign:
			aed = _add(root, "cac", "TaxTotal")
			_add(aed, "cbc", "TaxAmount", _amount(self.tax_total_aed), currencyID="AED")

	def _tax_category(self, parent, code: str, rate: float, reason: str | None = None, tag="TaxCategory"):
		category = _add(parent, "cac", tag)
		_add(category, "cbc", "ID", code)
		# An exempt category has no rate (rules ibr-121-ae and aligned-ibrp-e-05).
		if code != "E":
			_add(category, "cbc", "Percent", f"{flt(rate, 2):g}")
		if code == "E" and reason:
			_add(category, "cbc", "TaxExemptionReasonCode", reason)
		scheme = _add(category, "cac", "TaxScheme")
		_add(scheme, "cbc", "ID", "VAT")

	def _monetary_total(self, root):
		total = _add(root, "cac", "LegalMonetaryTotal")
		_add(total, "cbc", "LineExtensionAmount", _amount(self.line_total), currencyID=self.currency)
		_add(total, "cbc", "TaxExclusiveAmount", _amount(self.line_total), currencyID=self.currency)
		_add(total, "cbc", "TaxInclusiveAmount", _amount(self.inclusive_total), currencyID=self.currency)
		if self.rounding:
			_add(total, "cbc", "PayableRoundingAmount", _amount(self.rounding), currencyID=self.currency)
		_add(total, "cbc", "PayableAmount", _amount(self.payable), currencyID=self.currency)

	def _line(self, root, line: dict):
		row = line["row"]
		tag = "CreditNoteLine" if self.is_credit_note else "InvoiceLine"
		quantity_tag = "CreditedQuantity" if self.is_credit_note else "InvoicedQuantity"
		unit = UNIT_CODES.get(row.uom, DEFAULT_UNIT_CODE)

		element = _add(root, "cac", tag)
		_add(element, "cbc", "ID", row.idx)
		_add(element, "cbc", quantity_tag, f"{flt(line['qty'], 6):g}", unitCode=unit)
		_add(element, "cbc", "LineExtensionAmount", _amount(line["net"]), currencyID=self.currency)

		item = _add(element, "cac", "Item")
		_add(item, "cbc", "Description", (row.description or row.item_name or row.item_code)[:2000])
		_add(item, "cbc", "Name", (row.item_name or row.item_code)[:200])
		self._classification(item, row)
		self._tax_category(
			item, line["code"], line["rate"], self._exemption_reason(row), "ClassifiedTaxCategory"
		)

		price = _add(element, "cac", "Price")
		_add(price, "cbc", "PriceAmount", _price(line["net_price"]), currencyID=self.currency)
		_add(price, "cbc", "BaseQuantity", "1", unitCode=unit)
		discount = _add(price, "cac", "AllowanceCharge")
		_add(discount, "cbc", "ChargeIndicator", "false")
		_add(
			discount,
			"cbc",
			"Amount",
			_price(line["gross_price"] - line["net_price"]),
			currencyID=self.currency,
		)
		_add(discount, "cbc", "BaseAmount", _price(line["gross_price"]), currencyID=self.currency)

		# Line amounts in AED (BTAE-10, BTAE-08). An exempt line carries no VAT amount.
		extension = _add(element, "cac", "ItemPriceExtension")
		_add(extension, "cbc", "Amount", _amount(line["total"] * self.rate), currencyID="AED")
		if line["code"] != "E":
			tax = _add(extension, "cac", "TaxTotal")
			_add(tax, "cbc", "TaxAmount", _amount(line["vat"] * self.rate), currencyID="AED")

	def _classification(self, item, row):
		"""The item type, HS code (goods) and service accounting code (services). The service
		accounting code is an additional item identifier with the scheme SAC, not a classification
		code, and comes before the classification in the Item element."""
		item_type = self._item_type(row)
		hs_code = frappe.db.get_value("Item", row.item_code, "customs_tariff_number")
		sac_code = frappe.db.get_value("Item", row.item_code, "uae_sac_code")

		if item_type in ("Services", "Both") and sac_code:
			identification = _add(item, "cac", "AdditionalItemIdentification")
			_add(identification, "cbc", "ID", sac_code, schemeID="SAC")

		classification = _add(item, "cac", "CommodityClassification")
		_add(classification, "cbc", "CommodityCode", ITEM_TYPE_CODES[item_type])
		if item_type in ("Goods", "Both") and hs_code:
			_add(classification, "cbc", "ItemClassificationCode", hs_code, listID="HS")

	def _item_type(self, row) -> str:
		explicit = frappe.db.get_value("Item", row.item_code, "uae_item_type")
		if explicit:
			return explicit

		return "Goods" if frappe.db.get_value("Item", row.item_code, "is_stock_item") else "Services"


def _q_root(name: str) -> str:
	return f"{{{ROOTS[name]}}}{name}"
