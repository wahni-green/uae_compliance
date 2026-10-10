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
	FLAG_DEEMED_SUPPLY,
	FLAG_E_COMMERCE,
	FLAG_EXPORT,
	FLAG_FREE_TRADE_ZONE,
	FLAG_MARGIN_SCHEME,
	GTIN_LENGTHS,
	GTIN_SCHEME,
	INVOICE_TYPE_CODE,
	ITEM_TYPE_CODES,
	LEGAL_REGISTRATION_TYPES,
	NO_VAT_CATEGORY_CODES,
	OUT_OF_SCOPE_CREDIT_NOTE_TYPE_CODE,
	OUT_OF_SCOPE_INVOICE_TYPE_CODE,
	PAYMENT_MEANS_CODE,
	PROFILE_ID,
	REVERSE_CHARGE_CODE,
	REVERSE_CHARGE_NATURE_CODES,
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


def build_document(doc) -> tuple[bytes, dict, dict]:
	"""The XML, its summary and the document model (the same figures as plain data)."""
	return PintAEBuilder(doc).build_all()


def _q(prefix: str, tag: str) -> str:
	return f"{{{NAMESPACES[prefix]}}}{tag}"


def _add(parent, prefix: str, tag: str, text=None, **attributes):
	element = etree.SubElement(parent, _q(prefix, tag), **attributes)
	if text is not None:
		element.text = str(text)

	return element


def _amount(value) -> str:
	return f"{flt(value, 2):.2f}"


def _decimal(value, places: int) -> str:
	"""Fixed-point decimal text with at most `places` decimals and no trailing zeros, never scientific
	notation, so that the XML carries exactly the value the totals were calculated from."""
	text = f"{flt(value, places):.{places}f}"
	if "." in text:
		text = text.rstrip("0").rstrip(".")

	return text or "0"


def _price(value) -> str:
	return _decimal(value, 6)


class PintAEBuilder:
	def __init__(self, doc):
		self.doc = doc
		self.is_credit_note = bool(doc.get("is_return"))
		# ERPNext holds a return's quantities and amounts as negatives; a PINT AE credit note states
		# them as positive figures.
		self.sign = -1 if self.is_credit_note else 1
		self.root_name = "CreditNote" if self.is_credit_note else "Invoice"
		self.currency = doc.currency
		self.company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
		# The exchange rate is written with six decimals, so the AED figures use that same rate.
		self.rate = flt(doc.get("conversion_rate"), 6) or 1
		self.is_foreign = self.currency != "AED"
		self.lines: list[dict] = []
		self.breakdown: dict[tuple[str, float], dict] = {}

	# ------------------------------------------------------------------ assembly

	def build(self) -> tuple[bytes, dict]:
		xml, summary, _model = self.build_all(with_model=False)
		return xml, summary

	def build_all(self, with_model: bool = True) -> tuple[bytes, dict, dict]:
		"""The XML, its summary and the document model, from one set of calculations. Callers that
		need only the XML skip the model."""
		self._refuse_unsupported()
		self._compute_lines()
		self._refuse_flags_the_type_cannot_carry()
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
		return xml, self._summary(), self._model() if with_model else {}

	def _refuse_unsupported(self):
		doc = self.doc
		if self.company_currency != "AED":
			raise EInvoiceNotSupportedError(
				_("E-invoicing needs the company currency to be AED, not {0}.").format(self.company_currency)
			)

		if doc.get("uae_is_reverse_charge") and doc.get("uae_reverse_charge_type") not in (
			REVERSE_CHARGE_NATURE_CODES
		):
			raise EInvoiceNotSupportedError(
				_(
					"A {0} supply under the reverse charge cannot be sent as an e-invoice: the specification has no type of goods for it."
				).format(_(doc.get("uae_reverse_charge_type") or ""))
			)

		if doc.get("uae_is_margin_scheme"):
			# The specification reports a margin scheme invoice under the "standard rate additional
			# VAT" category (rule ibr-116-ae), which this builder does not produce yet.
			raise EInvoiceNotSupportedError(
				_("Profit margin scheme invoices cannot be sent as e-invoices yet.")
			)

	def _refuse_flags_the_type_cannot_carry(self):
		"""An out of scope invoice or credit note (480/81) cannot be a deemed supply, summary invoice or
		margin scheme invoice (rule ibr-157-ae)."""
		if self.type_code in (
			OUT_OF_SCOPE_INVOICE_TYPE_CODE,
			OUT_OF_SCOPE_CREDIT_NOTE_TYPE_CODE,
		) and self.doc.get("uae_is_deemed_supply"):
			raise EInvoiceNotSupportedError(
				_(
					"A deemed supply cannot be an out of scope or exempt only document. Add a taxable line or clear Deemed Supply."
				)
			)

	def _compute_lines(self):
		resolver = CategoryResolver()
		rates = get_item_wise_vat_rates(self.doc.get("taxes") or [], self.doc.company, is_output_vat_account)

		for row in self.doc.items:
			category = resolver.resolve(row)
			code = CATEGORY_CODES.get(category)
			if self._is_reverse_charge and code == "S":
				# The recipient accounts for the VAT: the line is reported at the standard rate with no
				# VAT charged (rules aligned-ibrp-ae-05 and ibr-162-ae).
				code = REVERSE_CHARGE_CODE
			if not code:
				raise EInvoiceNotSupportedError(
					_("Row #{0}: {1} supplies cannot be sent as e-invoices yet.").format(row.idx, _(category))
				)

			if code == "S":
				# A missing rate means the invoice does not say, so the standard rate applies; an explicit
				# 0% on a standard rated row has no PINT AE category to be reported under.
				if row.item_code in rates and not flt(rates[row.item_code]):
					raise EInvoiceNotSupportedError(
						_(
							"Row #{0}: a standard rated row with a 0% VAT rate cannot be sent as an e-invoice. Mark it Zero Rated or Exempt."
						).format(row.idx)
					)

				vat_rate = flt(rates.get(row.item_code)) or STANDARD_VAT_RATE
			elif code == REVERSE_CHARGE_CODE:
				vat_rate = STANDARD_VAT_RATE
			else:
				vat_rate = 0.0

			net = flt(row.net_amount * self.sign, 2)
			vat = flt(net * vat_rate / 100, 2) if code == "S" else 0.0
			qty = flt(row.qty * self.sign) or 1
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
			self.rounding = flt(flt(self.doc.rounded_total) * self.sign - self.inclusive_total, 2)

		self.payable = flt(self.inclusive_total + self.rounding, 2)
		self._refuse_untracked_amounts()
		self.tax_total_aed = flt(self.tax_total * self.rate, 2) if self.is_foreign else self.tax_total
		self.inclusive_total_aed = (
			flt(self.inclusive_total * self.rate, 2) if self.is_foreign else self.inclusive_total
		)

	def _refuse_untracked_amounts(self):
		"""The e-invoice is built from the item rows and the VAT on them. Anything else on the invoice
		(freight and other charges, a discount outside the rows, VAT that differs from the rows)
		would silently change the amount billed, so such an invoice is refused instead."""
		grand_total = flt(flt(self.doc.get("grand_total")) * self.sign, 2)
		if abs(self.inclusive_total - grand_total) > 0.02:
			raise EInvoiceNotSupportedError(
				_(
					"The invoice total {0} differs from its item rows and VAT ({1}). Charges, discounts or VAT outside the rows cannot be sent as an e-invoice yet."
				).format(grand_total, self.inclusive_total)
			)

	def _model(self) -> dict:
		"""The invoice as plain data, with the same figures as the XML, for providers whose API takes
		the invoice's fields instead of a PINT AE document."""
		doc = self.doc
		seller, buyer = self._collect_parties()
		return {
			"number": doc.name,
			"uuid": self.uuid,
			"type_code": self.type_code,
			"transaction_flags": self._transaction_flags(),
			"issue_date": getdate(doc.posting_date).isoformat(),
			"issue_time": f"{get_time(doc.get('posting_time') or '00:00:00').strftime('%H:%M:%S')}{UTC_OFFSET}",
			"due_date": getdate(doc.due_date).isoformat()
			if doc.get("due_date") and not self.is_credit_note and not self._is_deemed_supply
			else None,
			"vat_point_date": self._vat_point_date(),
			"currency": self.currency,
			"tax_currency": "AED" if self.is_foreign else None,
			"exchange_rate": self.rate if self.is_foreign else None,
			"buyer_reference": doc.get("po_no"),
			"credit_note": {
				"reason_code": doc.get("uae_credit_note_reason_code"),
				"preceding_number": doc.get("return_against"),
				"preceding_date": self._preceding_date(),
			}
			if self.is_credit_note
			else None,
			"payment_means_code": None
			if self.is_credit_note or self._is_deemed_supply
			else PAYMENT_MEANS_CODE,
			"beneficiary_id": self._beneficiary_id,
			"delivery": self._delivery_details(),
			"seller": seller,
			"buyer": buyer,
			"lines": [self._line_model(line) for line in self.lines],
			"breakdown": [dict(entry) for entry in self.breakdown.values()],
			"totals": {
				"line_total": self.line_total,
				"tax_exclusive": self.line_total,
				"tax_total": self.tax_total,
				"tax_total_aed": self.tax_total_aed,
				"tax_inclusive": self.inclusive_total,
				"tax_inclusive_aed": self.inclusive_total_aed,
				"rounding": self.rounding,
				"payable": self.payable,
			},
		}

	def _line_model(self, line: dict) -> dict:
		row = line["row"]
		item_type = self._item_type(row)
		return {
			"id": row.idx,
			"name": (row.item_name or row.item_code)[:200],
			"description": (row.description or row.item_name or row.item_code)[:2000],
			"item_type": item_type,
			"item_type_code": ITEM_TYPE_CODES[item_type],
			"hs_code": frappe.db.get_value("Item", row.item_code, "customs_tariff_number"),
			"sac_code": frappe.db.get_value("Item", row.item_code, "uae_sac_code"),
			"quantity": line["qty"],
			"unit_code": UNIT_CODES.get(row.uom, DEFAULT_UNIT_CODE),
			"gross_price": line["gross_price"],
			"net_price": line["net_price"],
			"discount": flt(line["gross_price"] - line["net_price"], 6),
			"net_amount": line["net"],
			"category_code": line["code"],
			"rate": line["rate"],
			"vat_amount": line["vat"],
			"total": line["total"],
			"exemption_reason_code": self._exemption_reason(row) if line["code"] == "E" else None,
			"nature_code": self._nature_code(line),
			"gtin": self._gtin(row) if line["code"] == REVERSE_CHARGE_CODE else None,
			"amount_aed": flt(line["total"] * self.rate, 2),
			"vat_amount_aed": flt(line["vat"] * self.rate, 2) if line["code"] != "E" else None,
		}

	def _vat_point_date(self):
		supply = self.doc.get("uae_supply_date")
		if supply and not self.is_credit_note and getdate(supply) < getdate(self.doc.posting_date):
			return getdate(supply).isoformat()

		return None

	def _preceding_date(self):
		if not self.doc.get("return_against"):
			return None

		date = frappe.db.get_value("Sales Invoice", self.doc.return_against, "posting_date")
		return getdate(date).isoformat() if date else None

	def _summary(self) -> dict:
		return {
			"uuid": self.uuid,
			"number": self.doc.name,
			"type_code": self.type_code,
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

	@property
	def type_code(self) -> str:
		"""380/381, or 480/81 when every line is exempt or out of scope: the specification keeps such
		lines off ordinary invoices and credit notes (rules ibr-151-ae and ibr-122-ae)."""
		only_no_vat = bool(self.lines) and all(line["code"] in NO_VAT_CATEGORY_CODES for line in self.lines)
		if self.is_credit_note:
			return OUT_OF_SCOPE_CREDIT_NOTE_TYPE_CODE if only_no_vat else CREDIT_NOTE_TYPE_CODE

		return OUT_OF_SCOPE_INVOICE_TYPE_CODE if only_no_vat else INVOICE_TYPE_CODE

	def _transaction_flags(self) -> str:
		flags = ["0"] * 8
		if self.doc.get("uae_is_free_zone_supply"):
			flags[FLAG_FREE_TRADE_ZONE] = "1"
		if self.doc.get("uae_is_deemed_supply"):
			flags[FLAG_DEEMED_SUPPLY] = "1"
		if self.doc.get("uae_is_margin_scheme"):
			flags[FLAG_MARGIN_SCHEME] = "1"
		if self.doc.get("uae_is_ecommerce_supply"):
			flags[FLAG_E_COMMERCE] = "1"
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
		if not self.is_credit_note and not self._is_deemed_supply and doc.get("due_date"):
			_add(root, "cbc", "DueDate", getdate(doc.due_date).isoformat())

		if self.is_credit_note:
			_add(root, "cbc", "CreditNoteTypeCode", self.type_code)
		else:
			_add(root, "cbc", "InvoiceTypeCode", self.type_code)

		if self._vat_point_date():
			_add(root, "cbc", "TaxPointDate", self._vat_point_date())

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
				elif agency == "PAS" and details.get("passport_country"):
					# The agency name of a passport is the ISO code of the country that issued it.
					attributes["schemeAgencyName"] = details["passport_country"]
			_add(legal, "cbc", "CompanyID", details["legal_id"], **attributes)

	@staticmethod
	def _country_code(country: str | None) -> str | None:
		code = frappe.db.get_value("Country", country, "code") if country else None
		return code.upper() if code else None

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

	def _collect_parties(self) -> tuple[dict, dict]:
		if not hasattr(self, "_parties_cache"):
			self._parties_cache = self._read_parties()

		return self._parties_cache

	def _read_parties(self) -> tuple[dict, dict]:
		"""The seller and the buyer as plain dictionaries, shared by the XML and the document model."""
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
				"uae_passport_country",
			],
			as_dict=True,
		)
		seller = {
			"endpoint": company.uae_tin or "",
			"name": doc.company,
			"legal_name": doc.company,
			"trn": company.uae_trn,
			"legal_id": company.uae_legal_registration_id,
			"legal_type": company.uae_legal_registration_type,
			"authority": company.uae_licence_authority,
			"passport_country": self._country_code(company.uae_passport_country),
			"address": self._address(doc.get("company_address")),
		}

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
				"uae_passport_country",
			],
			as_dict=True,
		)
		address = self._address(doc.get("customer_address"))
		# A buyer that is not on the network yet, or abroad, uses a predefined endpoint.
		endpoint = customer.uae_tin or (
			ENDPOINT_EXPORT if address.get("country") not in (None, "AE") else ENDPOINT_BUYER_NOT_ON_NETWORK
		)
		buyer = {
			"endpoint": endpoint,
			"name": customer.customer_name,
			"legal_name": doc.customer_name or customer.customer_name,
			"trn": customer.uae_trn,
			"legal_id": customer.uae_legal_registration_id,
			"legal_type": customer.uae_legal_registration_type,
			"authority": customer.uae_licence_authority,
			"passport_country": self._country_code(customer.uae_passport_country),
			"address": address,
		}
		return seller, buyer

	def _parties(self, root):
		seller, buyer = self._collect_parties()
		self._party(root, "AccountingSupplierParty", seller)
		self._party(root, "AccountingCustomerParty", buyer)
		self._beneficiary(root)
		self._delivery(root)

	@property
	def _is_reverse_charge(self) -> bool:
		return bool(self.doc.get("uae_is_reverse_charge"))

	@property
	def _is_deemed_supply(self) -> bool:
		return bool(self.doc.get("uae_is_deemed_supply"))

	@property
	def _beneficiary_id(self) -> str | None:
		"""The beneficiary of a free trade zone supply (BTAE-01)."""
		if not self.doc.get("uae_is_free_zone_supply"):
			return None

		return (self.doc.get("uae_free_zone_beneficiary_id") or "").strip()

	def _delivery_details(self) -> dict | None:
		"""Where an e-commerce supply was delivered: the shipping address, else the customer's."""
		if not self.doc.get("uae_is_ecommerce_supply"):
			return None

		address = self._address(self.doc.get("shipping_address_name") or self.doc.get("customer_address"))
		return {
			"date": getdate(self.doc.get("uae_supply_date") or self.doc.posting_date).isoformat(),
			"street": address.get("street"),
			"city": address.get("city"),
			"subdivision": address.get("subdivision"),
			"country": address.get("country") or "AE",
		}

	def _beneficiary(self, root):
		if self._beneficiary_id is None:
			return

		wrapper = _add(root, "cac", "BuyerCustomerParty")
		party = _add(wrapper, "cac", "Party")
		identification = _add(party, "cac", "PartyIdentification")
		_add(identification, "cbc", "ID", self._beneficiary_id)

	def _delivery(self, root):
		details = self._delivery_details()
		if not details:
			return

		delivery = _add(root, "cac", "Delivery")
		_add(delivery, "cbc", "ActualDeliveryDate", details["date"])
		location = _add(delivery, "cac", "DeliveryLocation")
		postal = _add(location, "cac", "Address")
		if details["street"]:
			_add(postal, "cbc", "StreetName", details["street"])
		if details["city"]:
			_add(postal, "cbc", "CityName", details["city"])
		if details["subdivision"]:
			_add(postal, "cbc", "CountrySubentity", details["subdivision"])
		country = _add(postal, "cac", "Country")
		_add(country, "cbc", "IdentificationCode", details["country"])

	def _payment_means(self, root):
		# A credit note carries no payment means, and neither does a deemed supply, which has no
		# consideration (rule ibr-191-ae).
		if self.is_credit_note or self._is_deemed_supply:
			return

		means = _add(root, "cac", "PaymentMeans")
		_add(means, "cbc", "PaymentMeansCode", PAYMENT_MEANS_CODE, name="Instrument Not Defined")

	def _tax_totals(self, root):
		if self.is_foreign:
			exchange = _add(root, "cac", "TaxExchangeRate")
			_add(exchange, "cbc", "SourceCurrencyCode", self.currency)
			_add(exchange, "cbc", "TargetCurrencyCode", "AED")
			_add(exchange, "cbc", "CalculationRate", _decimal(self.rate, 6))

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
		# An exempt or out of scope category has no rate (rules ibr-121-ae, aligned-ibrp-e-05 and
		# aligned-ibrp-o-05).
		if code not in NO_VAT_CATEGORY_CODES:
			_add(category, "cbc", "Percent", _decimal(rate, 2))
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
		_add(element, "cbc", quantity_tag, _decimal(line["qty"], 6), unitCode=unit)
		_add(element, "cbc", "LineExtensionAmount", _amount(line["net"]), currencyID=self.currency)

		item = _add(element, "cac", "Item")
		_add(item, "cbc", "Description", (row.description or row.item_name or row.item_code)[:2000])
		_add(item, "cbc", "Name", (row.item_name or row.item_code)[:200])
		self._classification(item, row, line)
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
		# Only an exempt line omits the VAT amount; an out of scope line states 0 (rule ibr-104-ae).
		if line["code"] != "E":
			tax = _add(extension, "cac", "TaxTotal")
			_add(tax, "cbc", "TaxAmount", _amount(line["vat"] * self.rate), currencyID="AED")

	def _nature_code(self, line: dict) -> str | None:
		"""The type of goods subject to the reverse charge (BTAE-09)."""
		if line["code"] != REVERSE_CHARGE_CODE:
			return None

		return REVERSE_CHARGE_NATURE_CODES.get(self.doc.get("uae_reverse_charge_type"))

	def _gtin(self, row) -> str | None:
		"""The item's GTIN: the first barcode of 8, 12, 13 or 14 digits (rule ibr-174-ae). Read once per
		item and build, for the XML and the provider model."""
		cache = self.__dict__.setdefault("_gtin_cache", {})
		if row.item_code not in cache:
			cache[row.item_code] = None
			for barcode in frappe.get_all(
				"Item Barcode", filters={"parent": row.item_code}, pluck="barcode", order_by="idx asc"
			):
				digits = (barcode or "").strip()
				if digits.isdigit() and len(digits) in GTIN_LENGTHS:
					cache[row.item_code] = digits
					break

		return cache[row.item_code]

	def _classification(self, item, row, line: dict | None = None):
		"""The item type, HS code (goods) and service accounting code (services). The service
		accounting code is an additional item identifier with the scheme SAC, not a classification
		code, and comes before the classification in the Item element."""
		item_type = self._item_type(row)
		hs_code = frappe.db.get_value("Item", row.item_code, "customs_tariff_number")
		sac_code = frappe.db.get_value("Item", row.item_code, "uae_sac_code")
		is_reverse_charge = bool(line) and line["code"] == REVERSE_CHARGE_CODE

		# A reverse charge line names the item by its GTIN, which comes before the other identifiers.
		if is_reverse_charge and self._gtin(row):
			standard = _add(item, "cac", "StandardItemIdentification")
			_add(standard, "cbc", "ID", self._gtin(row), schemeID=GTIN_SCHEME)

		if item_type in ("Services", "Both") and sac_code:
			identification = _add(item, "cac", "AdditionalItemIdentification")
			_add(identification, "cbc", "ID", sac_code, schemeID="SAC")

		classification = _add(item, "cac", "CommodityClassification")
		if is_reverse_charge:
			_add(classification, "cbc", "NatureCode", self._nature_code(line) or "")
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
