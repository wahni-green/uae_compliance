import frappe
from frappe import _
from frappe.utils import formatdate


def get_exchange_rate_disclosure(doc) -> str | None:
	"""The exchange rate used to arrive at the AED figures of a foreign-currency document, which a
	tax invoice must state (ER Art 59(1)(k)). None for a document in company currency."""
	if not doc.get("currency") or not doc.get("company"):
		return None

	company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	if doc.currency == company_currency:
		return None

	return _("Exchange rate: 1 {0} = {1} {2} (as on {3})").format(
		doc.currency, doc.conversion_rate, company_currency, formatdate(doc.get("posting_date"))
	)
