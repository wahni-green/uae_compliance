import frappe
from frappe import _
from frappe.utils import flt

from uae_compliance.uae_compliance.constants import (
	STANDARD_VAT_RATE,
	TOURIST_MIN_PURCHASE,
	TOURIST_REFUND_CAP,
)
from uae_compliance.uae_compliance.constants.excise_rates import PER_LITRE
from uae_compliance.uae_compliance.utils.print_data import get_output_vat_amount
from uae_compliance.uae_compliance.utils.tax_account import get_excise_tax_account

# Both the margin figures and the currency tolerance are in document currency.
TOLERANCE = 0.01


def validate_margin_scheme(doc) -> None:
	"""Profit margin scheme (ER Art 29): VAT is due on the margin only, and the VAT is part of the
	price. The row amount is the price before that VAT, so the VAT due is the standard rate of
	(net amount less purchase price), and the VAT posted to the Output VAT account has to equal it,
	otherwise the invoice and the VAT return would disagree. Returns are not checked: their rows
	carry the original purchase prices."""
	if not doc.get("uae_is_margin_scheme") or doc.get("is_return"):
		return

	for row in doc.items:
		if row.get("uae_vat_category") != "Standard Rated":
			frappe.throw(
				_("Row #{0}: the profit margin scheme only applies to standard rated supplies.").format(
					row.idx
				),
				title=_("Profit Margin Scheme"),
			)

		if flt(row.get("uae_margin_purchase_price")) <= 0:
			frappe.throw(
				_("Row #{0}: enter the purchase price of the goods for the profit margin scheme.").format(
					row.idx
				),
				title=_("Profit Margin Scheme"),
			)

	expected = flt(get_expected_margin_vat(doc), 2)
	charged = get_output_vat_amount(doc)
	if charged is None:
		frappe.throw(
			_("Configure the Output VAT Account in UAE Compliance Settings first."),
			title=_("VAT Accounts Not Configured"),
		)

	if abs(flt(charged, 2) - expected) > TOLERANCE:
		frappe.throw(
			_(
				"The VAT on a profit margin invoice must be {0}% of the margin ({1}), but {2} was posted"
				" to the Output VAT Account."
			).format(STANDARD_VAT_RATE, frappe.bold(expected), frappe.bold(flt(charged, 2))),
			title=_("Profit Margin VAT Mismatch"),
		)


def get_expected_margin_vat(doc) -> float:
	"""The standard rate of the margin of every row. A row sold at a loss owes nothing and does not
	reduce the VAT of the others."""
	return sum(
		max(0.0, flt(row.net_amount) - flt(row.get("uae_margin_purchase_price"))) * STANDARD_VAT_RATE / 100
		for row in doc.items
	)


def validate_tourist_refund(doc) -> None:
	"""Tax refunds for tourists (FTA Decision 2 of 2018 as amended): the refund cannot exceed the VAT
	charged, the purchase must be at least AED 250, and a tourist is refunded at most AED 35,000 in
	cash in 24 hours. The refund is recorded in the invoice currency."""
	refund = flt(doc.get("uae_tourist_refund"))
	if not refund:
		return

	if doc.get("is_return") or refund < 0:
		frappe.throw(
			_("A tourist refund must be a positive amount on the original sale, not on a return."),
			title=_("Invalid Tourist Refund"),
		)

	if not any(row.get("uae_vat_category") == "Standard Rated" for row in doc.items):
		frappe.throw(
			_("A tourist refund needs at least one standard rated row."), title=_("Invalid Tourist Refund")
		)

	rate = flt(doc.get("conversion_rate")) or 1
	if flt(doc.get("base_grand_total")) < TOURIST_MIN_PURCHASE:
		frappe.throw(
			_("The purchase must be at least AED {0} for a tourist refund.").format(TOURIST_MIN_PURCHASE),
			title=_("Invalid Tourist Refund"),
		)

	if refund * rate > TOURIST_REFUND_CAP:
		frappe.throw(
			_("A tourist refund cannot exceed AED {0}.").format(TOURIST_REFUND_CAP),
			title=_("Invalid Tourist Refund"),
		)

	charged = get_output_vat_amount(doc) or 0
	if refund > flt(charged, 2) + TOLERANCE:
		frappe.throw(
			_("The refund of {0} is more than the {1} of VAT charged on this invoice.").format(
				refund, flt(charged, 2)
			),
			title=_("Invalid Tourist Refund"),
		)


def get_expected_excise(doc) -> float:
	"""The excise tax due on the rows with an excise category, in company currency: a percentage of
	the net amount (taken as the excise price) or an amount per litre."""
	total = 0.0
	rate = flt(doc.get("conversion_rate")) or 1
	for row in doc.items:
		category = frappe.get_cached_value("Item", row.item_code, "uae_excise_category")
		if not category:
			continue

		rate_type, excise_rate = frappe.get_cached_value("UAE Excise Rate", category, ["rate_type", "rate"])
		if rate_type == PER_LITRE:
			litres = flt(row.qty) * flt(
				frappe.get_cached_value("Item", row.item_code, "uae_excise_volume_litres")
			)
			total += litres * flt(excise_rate)
		else:
			total += flt(row.net_amount) * rate * flt(excise_rate) / 100

	return total


def warn_if_excise_missing(doc) -> None:
	"""Excise goods should carry excise tax on the Excise Tax account. This only warns, because
	goods sold from or to a designated zone may not be subject to it."""
	expected = flt(get_expected_excise(doc), 2)
	if not expected:
		return

	account = get_excise_tax_account(doc.get("company"))
	if not account:
		frappe.msgprint(
			_("This invoice has excise goods but no Excise Tax Account is set in UAE Compliance Settings."),
			indicator="orange",
			alert=True,
		)
		return

	charged = sum(
		flt(tax.get("base_tax_amount"))
		for tax in doc.get("taxes") or []
		if tax.get("account_head") == account
	)
	if abs(flt(charged, 2) - expected) > TOLERANCE:
		frappe.msgprint(
			_(
				"The excise tax on this invoice is {0}, but {1} is expected from the excise goods on it."
			).format(flt(charged, 2), expected),
			indicator="orange",
			alert=True,
		)
