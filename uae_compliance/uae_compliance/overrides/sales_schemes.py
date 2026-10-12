from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, flt, format_date, get_datetime, getdate, nowdate

from uae_compliance.uae_compliance.constants import (
	STANDARD_VAT_RATE,
	TOURIST_EXPORT_DAYS,
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

	if flt(doc.get("base_grand_total")) < TOURIST_MIN_PURCHASE:
		frappe.throw(
			_("The purchase must be at least AED {0} for a tourist refund.").format(TOURIST_MIN_PURCHASE),
			title=_("Invalid Tourist Refund"),
		)

	refund_in_aed = get_refund_in_aed(refund, doc.get("conversion_rate"), doc.company, doc.posting_date)
	if refund_in_aed > TOURIST_REFUND_CAP:
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

	if not (doc.get("uae_tourist_passport") and doc.get("uae_tourist_departure_date")):
		frappe.throw(
			_("A tourist refund needs the tourist's passport number and departure date."),
			title=_("Invalid Tourist Refund"),
		)

	validate_tourist_departure(doc)
	validate_tourist_daily_cap(doc, refund_in_aed)


def validate_tourist_departure(doc) -> None:
	"""The goods must leave the UAE with the tourist within 90 days of the supply."""
	supply = getdate(doc.get("uae_supply_date") or doc.get("posting_date") or nowdate())
	departure = getdate(doc.get("uae_tourist_departure_date"))
	if departure < supply:
		frappe.throw(
			_("The tourist cannot depart before the supply date, {0}.").format(format_date(supply)),
			title=_("Invalid Tourist Refund"),
		)

	if departure > add_days(supply, TOURIST_EXPORT_DAYS):
		frappe.throw(
			_("The goods must leave the UAE within {0} days of the supply. The last day was {1}.").format(
				TOURIST_EXPORT_DAYS, format_date(add_days(supply, TOURIST_EXPORT_DAYS))
			),
			title=_("Invalid Tourist Refund"),
		)


def get_refund_in_aed(refund, conversion_rate, company: str, on) -> float:
	"""A refund in invoice currency, in AED: through the invoice's conversion rate to the company
	currency, then to AED when the company does not keep its books in AED."""
	amount = flt(refund) * (flt(conversion_rate) or 1)
	currency = frappe.get_cached_value("Company", company, "default_currency")
	if not currency or currency == "AED":
		return amount

	from erpnext.setup.utils import get_exchange_rate

	return amount * flt(get_exchange_rate(currency, "AED", on) or 1)


def validate_tourist_daily_cap(doc, refund: float) -> None:
	"""A tourist is refunded at most AED 35,000 in 24 hours, across invoices. The tourist is known by
	the passport number (kept upper case and trimmed). Submitted invoices of every company count; this
	one is checked against every 24-hour window it falls in, so a refund 23 hours before and another 23
	hours after are not added together. A lock per passport makes simultaneous saves wait for each
	other."""
	passport = (doc.get("uae_tourist_passport") or "").strip().upper()
	doc.uae_tourist_passport = passport
	posted = get_datetime(f"{getdate(doc.posting_date)} {doc.get('posting_time') or '00:00:00'}")
	day = timedelta(hours=24)

	lock_passport(passport)
	# A locking read sees the latest committed rows, not the snapshot this transaction started with,
	# so the refund the other request has just committed is counted.
	invoice = frappe.qb.DocType("Sales Invoice")
	others = (
		frappe.qb.from_(invoice)
		.select(
			invoice.posting_date,
			invoice.posting_time,
			invoice.uae_tourist_refund,
			invoice.conversion_rate,
			invoice.company,
		)
		.where(
			(invoice.uae_tourist_passport == passport)
			& (invoice.uae_tourist_refund != 0)
			& (invoice.docstatus == 1)
			& (invoice.name != (doc.name or ""))
			& invoice.posting_date.between(add_days(posted.date(), -1), add_days(posted.date(), 1))
		)
		.for_update()
		.run(as_dict=True)
	)
	events = [(posted, refund)]
	for other in others:
		at = get_datetime(f"{other.posting_date} {other.posting_time}")
		if abs(at - posted) < day:
			events.append(
				(
					at,
					get_refund_in_aed(
						other.uae_tourist_refund, other.conversion_rate, other.company, other.posting_date
					),
				)
			)

	# The busiest 24 hours that begin at one of the refunds and include this one.
	total = max(
		sum(amount for at, amount in events if start <= at < start + day)
		for start, _amount in events
		if start <= posted < start + day
	)
	if total > TOURIST_REFUND_CAP + TOLERANCE:
		frappe.throw(
			_(
				"This tourist is refunded AED {0} within 24 hours with this invoice. The limit is AED {1}."
			).format(flt(total, 2), TOURIST_REFUND_CAP),
			title=_("Invalid Tourist Refund"),
		)


def lock_passport(passport: str) -> None:
	"""Held until the transaction ends, so two invoices for one passport are checked one after the
	other and the second sees the first."""
	name = f"uae_tourist_{passport}"[:64]
	if frappe.db.sql("select get_lock(%s, 10)", name)[0][0] != 1:
		frappe.throw(_("Another refund for this passport is being saved. Try again."))

	release = lambda: frappe.db.sql("select release_lock(%s)", name)  # noqa: E731
	frappe.db.after_commit.add(release)
	frappe.db.after_rollback.add(release)


def get_expected_excise(doc) -> float:
	"""The excise tax due on the rows with an excise category, in company currency: a percentage of
	the net amount (taken as the excise price) or an amount per litre of the stock quantity. Only a
	rate that is active and in force on the invoice date applies."""
	total = 0.0
	conversion = flt(doc.get("conversion_rate")) or 1
	on = getdate(doc.get("posting_date") or nowdate())

	for row in doc.items:
		category = frappe.get_cached_value("Item", row.item_code, "uae_excise_category")
		if not category:
			continue

		rate_type, excise_rate, is_active, effective_from = frappe.get_cached_value(
			"UAE Excise Rate", category, ["rate_type", "rate", "is_active", "effective_from"]
		)
		if not is_active or (effective_from and getdate(effective_from) > on):
			continue

		if rate_type == PER_LITRE:
			volume = flt(frappe.get_cached_value("Item", row.item_code, "uae_excise_volume_litres"))
			total += (flt(row.get("stock_qty")) or flt(row.qty)) * volume * flt(excise_rate)
		else:
			total += flt(row.net_amount) * conversion * flt(excise_rate) / 100

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
