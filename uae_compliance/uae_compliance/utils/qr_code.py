import frappe
import pyqrcode
from frappe.utils import fmt_money

from uae_compliance.uae_compliance.utils.print_data import get_output_vat_amount
from uae_compliance.uae_compliance.utils.tax_account import is_einvoicing_company


def get_tax_invoice_qr_code(doc) -> str | None:
	"""Base64 PNG data URI for the QR code on a tax invoice, or None to print none.

	The FTA publishes no QR specification for tax invoices, and e-invoices carry no QR code at all
	(MoF Guidelines s5.3). So this is off by default (UAE Compliance Settings > Show QR Code on Tax
	Invoices), never printed for a company that issues e-invoices, and its payload is plain
	labelled text, not a government-defined structure."""
	company = doc.get("company")
	if not company or is_einvoicing_company(company):
		return None

	if not frappe.get_cached_doc("UAE Compliance Settings").show_qr_code:
		return None

	company_trn = frappe.get_cached_value("Company", company, "uae_trn")
	if not company_trn:
		return None

	currency = frappe.get_cached_value("Company", company, "default_currency")
	vat = get_output_vat_amount(doc, base=True)
	vat_line = (
		"VAT: not available (Output VAT Account not configured)"
		if vat is None
		else f"VAT: {fmt_money(vat, currency=currency)}"
	)
	payload = "\n".join(
		[
			f"Seller: {company}",
			f"TRN: {company_trn}",
			f"Invoice: {doc.get('name') or ''}",
			f"Date: {doc.get('posting_date') or ''}",
			f"Total: {fmt_money(doc.get('base_grand_total') or 0, currency=currency)}",
			vat_line,
		]
	)

	# utf-8 is required: a company name in Arabic would otherwise raise UnicodeEncodeError.
	qr_code = pyqrcode.create(payload, encoding="utf-8")
	return "data:image/png;base64," + qr_code.png_as_base64_str(scale=4)
