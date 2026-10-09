import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class UAEEInvoiceLog(Document):
	"""The record of one e-invoice: the XML sent, the provider's answers and where it stands. E-invoices
	have to be kept for five years, so a log cannot be deleted before its retention date."""

	def on_trash(self):
		if self.retain_until and getdate(self.retain_until) >= getdate(nowdate()):
			frappe.throw(
				_("E-invoices must be kept until {0}.").format(
					frappe.format(self.retain_until, {"fieldtype": "Date"})
				),
				title=_("Retention Period"),
			)

	@frappe.whitelist()
	def retry(self):
		"""Rebuild and send the document again after a failure, a rejection or fixing its data."""
		from uae_compliance.uae_compliance.einvoice.pipeline import retry_log

		frappe.has_permission(self.doctype, "write", doc=self, throw=True)
		retry_log(self.name)

	@frappe.whitelist()
	def check_status(self):
		from uae_compliance.uae_compliance.einvoice.pipeline import poll_log

		frappe.has_permission(self.doctype, "write", doc=self, throw=True)
		poll_log(self.name)
