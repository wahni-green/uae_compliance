import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, flt, getdate

from uae_compliance.uae_compliance.constants import (
	ADJUSTMENT_ANNUAL_APPORTIONMENT,
	ADJUSTMENT_BAD_DEBT_RELIEF,
	ADJUSTMENT_BAD_DEBT_REPAYMENT,
	BAD_DEBT_MONTHS,
)
from uae_compliance.uae_compliance.utils.print_data import get_output_vat_amount
from uae_compliance.uae_compliance.utils.vat_return.apportionment import get_annual_apportionment


class UAEVATAdjustment(Document):
	def validate(self):
		if self.adjustment_type == ADJUSTMENT_BAD_DEBT_RELIEF:
			self.validate_bad_debt_relief()
		elif self.adjustment_type == ADJUSTMENT_BAD_DEBT_REPAYMENT:
			self.validate_bad_debt_repayment()
		elif self.adjustment_type == ADJUSTMENT_ANNUAL_APPORTIONMENT:
			self.validate_annual_apportionment()

	def before_submit(self):
		if not flt(self.vat_amount) and not flt(self.amount):
			frappe.throw(_("Enter the VAT adjustment before submitting."))

		self.validate_period_is_open()

		if self.adjustment_type == ADJUSTMENT_BAD_DEBT_RELIEF:
			# Two relief claims for one invoice could be submitted at the same moment and each pass
			# the limit alone, so the invoice is locked while the limit is checked again.
			frappe.db.get_value("Sales Invoice", self.sales_invoice, "name", for_update=True)
			self.validate_within_invoice_vat()

	def validate_period_is_open(self):
		"""An adjustment is reported in the return of its period, which cannot change once Filed."""
		filed = frappe.db.get_value(
			"UAE VAT Return",
			{
				"company": self.company,
				"status": "Filed",
				"from_date": ["<=", self.posting_date],
				"to_date": [">=", self.posting_date],
			},
			"name",
		)
		if filed:
			frappe.throw(
				_(
					"The return {0} for this period is already Filed. Date the adjustment in an open period."
				).format(filed),
				title=_("Period Already Filed"),
			)

	def validate_annual_apportionment(self):
		"""One annual apportionment per company and tax year, or the same difference is reported
		twice."""
		if not (self.period_from and self.period_to):
			return

		overlapping = frappe.db.get_value(
			"UAE VAT Adjustment",
			{
				"company": self.company,
				"adjustment_type": ADJUSTMENT_ANNUAL_APPORTIONMENT,
				"docstatus": ["!=", 2],
				"name": ["!=", self.name],
				"period_from": ["<=", self.period_to],
				"period_to": [">=", self.period_from],
			},
			"name",
		)
		if overlapping:
			frappe.throw(
				_("{0} already adjusts the apportionment of an overlapping tax year.").format(overlapping),
				title=_("Duplicate Annual Apportionment"),
			)

	def validate_bad_debt_relief(self):
		"""Decree-Law Art 64: a supplier may reduce its output tax when the supply was made and the tax
		charged and paid, the consideration is written off, more than six months have passed since the
		supply, and the recipient has been told. The VAT adjustment is a negative figure."""
		if not self.sales_invoice:
			return

		invoice = frappe.db.get_value(
			"Sales Invoice",
			self.sales_invoice,
			["company", "docstatus", "is_return", "posting_date", "uae_supply_date", "uae_emirate"],
			as_dict=True,
		)
		if invoice.company != self.company or invoice.docstatus != 1 or invoice.is_return:
			frappe.throw(
				_("{0} must be a submitted sales invoice (not a return) of {1}.").format(
					self.sales_invoice, self.company
				)
			)

		supply_date = getdate(invoice.uae_supply_date or invoice.posting_date)
		if getdate(self.posting_date) <= add_months(supply_date, BAD_DEBT_MONTHS):
			frappe.throw(
				_(
					"Bad debt relief needs more than {0} months to have passed since the supply on {1}."
				).format(BAD_DEBT_MONTHS, frappe.format(supply_date, {"fieldtype": "Date"})),
				title=_("Too Early for Bad Debt Relief"),
			)

		if not self.emirate:
			self.emirate = invoice.uae_emirate
		elif invoice.uae_emirate and self.emirate != invoice.uae_emirate:
			frappe.throw(
				_("The relief is reported in {0}, the emirate of {1}, not {2}.").format(
					invoice.uae_emirate, self.sales_invoice, self.emirate
				),
				title=_("Wrong Emirate"),
			)

		if not self.customer_notified or not self.notification_date:
			frappe.throw(
				_("The customer must be notified of the write-off. Tick it and enter the notification date."),
				title=_("Customer Not Notified"),
			)

		for label, date in (
			(_("Written Off On"), self.write_off_date),
			(_("Notification Date"), self.notification_date),
		):
			if not date or getdate(date) > getdate(self.posting_date):
				frappe.throw(
					_("{0} is required and cannot be after the adjustment date.").format(label),
					title=_("Conditions Not Met"),
				)

		self.validate_negative_vat()
		self.validate_within_invoice_vat()

	def validate_bad_debt_repayment(self):
		"""The recipient must reduce its input tax if it has not paid more than six months after the
		supplier's notice."""
		if not self.purchase_invoice:
			return

		invoice = frappe.db.get_value(
			"Purchase Invoice", self.purchase_invoice, ["company", "docstatus", "is_return"], as_dict=True
		)
		if invoice.company != self.company or invoice.docstatus != 1 or invoice.is_return:
			frappe.throw(
				_("{0} must be a submitted purchase invoice (not a return) of {1}.").format(
					self.purchase_invoice, self.company
				)
			)

		if not self.notification_date or getdate(self.notification_date) > getdate(self.posting_date):
			frappe.throw(
				_("The supplier's notification date is required and cannot be after the adjustment date."),
				title=_("Conditions Not Met"),
			)

		if getdate(self.posting_date) <= add_months(getdate(self.notification_date), BAD_DEBT_MONTHS):
			frappe.throw(
				_("More than {0} months must have passed since the supplier's notice on {1}.").format(
					BAD_DEBT_MONTHS, frappe.format(self.notification_date, {"fieldtype": "Date"})
				),
				title=_("Too Early"),
			)

		self.validate_negative_vat()

	def validate_negative_vat(self):
		if flt(self.vat_amount) >= 0:
			frappe.throw(
				_("The VAT adjustment for {0} must be a negative figure.").format(_(self.adjustment_type)),
				title=_("Invalid Adjustment"),
			)

	def validate_within_invoice_vat(self):
		"""The relief cannot exceed the VAT charged on the invoice, counting earlier reliefs."""
		invoice = frappe.get_doc("Sales Invoice", self.sales_invoice)
		charged = get_output_vat_amount(invoice, base=True) or 0

		relieved = frappe.db.get_all(
			"UAE VAT Adjustment",
			filters={
				"sales_invoice": self.sales_invoice,
				"adjustment_type": ADJUSTMENT_BAD_DEBT_RELIEF,
				"docstatus": 1,
				"name": ["!=", self.name],
			},
			fields=["sum(vat_amount) as total"],
		)
		already = abs(flt(relieved[0].total)) if relieved else 0

		if abs(flt(self.vat_amount)) + already > flt(charged, 2):
			frappe.throw(
				_("The relief of {0} plus {1} already relieved exceeds the {2} of VAT on {3}.").format(
					abs(flt(self.vat_amount)), already, flt(charged, 2), self.sales_invoice
				),
				title=_("Relief Exceeds VAT Charged"),
			)

	@frappe.whitelist()
	def calculate_apportionment(self):
		"""Fill the annual apportionment from the Filed returns of the tax year."""
		if self.adjustment_type != ADJUSTMENT_ANNUAL_APPORTIONMENT:
			frappe.throw(_("Only an Annual Apportionment can be calculated."))

		if not (self.company and self.period_from and self.period_to):
			frappe.throw(_("Company, Tax Year Start and Tax Year End are required."))

		frappe.has_permission("Company", "read", doc=self.company, throw=True)
		result = get_annual_apportionment(self.company, self.period_from, self.period_to)
		self.vat_amount = result["adjustment"]
		self.remarks = _(
			"Annual ratio {0}%. Residual input VAT {1}, recoverable {2}, claimed {3} across {4} filed returns."
		).format(
			result["annual_ratio"],
			result["residual_input_vat"],
			result["annual_recoverable"],
			result["claimed"],
			result["returns"],
		)
