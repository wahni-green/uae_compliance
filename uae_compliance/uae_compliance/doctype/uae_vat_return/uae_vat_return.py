import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from uae_compliance.uae_compliance.constants.vat_return import (
	BOX_EXEMPT,
	BOX_EXPENSE_TOTALS,
	BOX_IMPORT_ADJUSTMENTS,
	BOX_IMPORTS,
	BOX_REVERSE_CHARGE_EXPENSES,
	BOX_REVERSE_CHARGE_SUPPLIES,
	BOX_SALES_TOTALS,
	BOX_STANDARD_RATED_EXPENSES,
	BOX_TOURIST_REFUNDS,
	BOX_ZERO_RATED,
	EMIRATE_BOX_CODES,
)
from uae_compliance.uae_compliance.utils.tax_account import get_output_vat_account
from uae_compliance.uae_compliance.utils.vat_return.apportionment import (
	get_period_supplies,
	get_recovery_ratio,
)
from uae_compliance.uae_compliance.utils.vat_return.group import get_group_rows, get_return_companies
from uae_compliance.uae_compliance.utils.vat_return.period import (
	get_due_date,
	get_filing_frequency,
	get_period_type,
	get_period_warning,
)
from uae_compliance.uae_compliance.utils.vat_return.sections.adjustments import get_adjustments
from uae_compliance.uae_compliance.utils.vat_return.sections.purchase_boxes import get_purchase_boxes
from uae_compliance.uae_compliance.utils.vat_return.sections.sales_boxes import (
	get_margin_scheme,
	get_sales_boxes,
)
from uae_compliance.uae_compliance.utils.vat_return.sections.standard_rated_by_emirate import (
	get_standard_rated_by_emirate,
)
from uae_compliance.uae_compliance.utils.vat_return.totals import (
	get_expense_totals,
	get_payable_tax,
	get_sales_totals,
	get_total_due_tax,
	get_total_recoverable_tax,
)


class UAEVATReturn(Document):
	def validate(self):
		if self.from_date and self.to_date:
			if getdate(self.from_date) > getdate(self.to_date):
				frappe.throw(_("From Date cannot be after To Date"))

			self.period_type = get_period_type(self.from_date, self.to_date)
			self.due_date = get_due_date(self.to_date)
			self.warn_if_period_mismatch()

		self.validate_filed_is_immutable()
		self.validate_can_be_filed()
		self._clear_boxes_if_stale()

	def warn_if_period_mismatch(self):
		# A warning, not an error: the FTA may assign other periods, for example a first period that
		# starts on the registration date.
		message = get_period_warning(
			self.from_date, self.to_date, get_filing_frequency(self.company) if self.company else None
		)
		if message:
			frappe.msgprint(message, indicator="orange", alert=True)

	def validate_filed_is_immutable(self):
		"""Once the persisted document is Filed, every further save is rejected. The only save still
		allowed is the Draft to Filed transition itself."""
		if self.is_new():
			return

		if self._get_locked_persisted_status() == "Filed":
			frappe.throw(_("A Filed return cannot be modified."), title=_("Return Already Filed"))

	def validate_can_be_filed(self):
		"""A return may only become Filed through generated, current boxes, whichever way the status
		is set. Without this a direct save with status Filed would skip the checks mark_as_filed()
		makes and lock an empty return permanently."""
		if self.status != "Filed":
			return

		if not self.boxes:
			frappe.throw(_("Generate the return before filing it."))

		if self._boxes_are_stale():
			frappe.throw(
				_(
					"The generated boxes no longer match this return's Company, From Date and To Date. Regenerate the return before filing it."
				)
			)

	def _boxes_are_stale(self) -> bool:
		"""`boxes` is a snapshot computed from company, from date and to date, which stay editable.
		generate_return() stamps `generated_for_*`; any difference means the snapshot is stale. This
		does not use has_value_changed(), which would wipe boxes just generated for a changed date."""
		if not self.boxes:
			return False

		if not (self.generated_for_company and self.generated_for_from_date and self.generated_for_to_date):
			return True

		return not (
			self.company == self.generated_for_company
			and getdate(self.from_date) == getdate(self.generated_for_from_date)
			and getdate(self.to_date) == getdate(self.generated_for_to_date)
		)

	def _clear_boxes_if_stale(self):
		if not self._boxes_are_stale():
			return

		self.boxes = []
		self.total_due_tax = 0
		self.total_recoverable_tax = 0
		self.payable_tax = 0
		self.generated_for_company = None
		self.generated_for_from_date = None
		self.generated_for_to_date = None

		frappe.msgprint(
			_(
				"Company, From Date or To Date changed since the return was generated. The boxes were cleared. Regenerate the return."
			),
			indicator="orange",
			alert=True,
		)

	def on_trash(self):
		if self._get_locked_persisted_status() == "Filed":
			frappe.throw(_("A Filed return cannot be deleted."), title=_("Return Already Filed"))

	def _get_locked_persisted_status(self) -> str | None:
		# for_update takes a row lock for the rest of the transaction, so a concurrent save or delete
		# waits and then reads the committed status instead of racing past a stale one.
		return frappe.db.get_value(self.doctype, self.name, "status", for_update=True)

	@frappe.whitelist()
	def generate_return(self):
		"""Recompute every box from the period's transactions and replace `boxes`. Safe to repeat
		while Draft; refused once Filed."""
		if self.status == "Filed":
			frappe.throw(_("Cannot regenerate a Filed return."))

		if not (self.company and self.from_date and self.to_date):
			frappe.throw(_("Company, From Date and To Date are required before generating a return."))

		if not get_output_vat_account(self.company):
			frappe.throw(
				_("Configure the Output VAT Account for {0} in UAE Compliance Settings first.").format(
					self.company
				),
				title=_("VAT Accounts Not Configured"),
			)

		sales_rows = get_group_rows("Sales Invoice", self.company, self.from_date, self.to_date)
		purchase_rows = get_group_rows("Purchase Invoice", self.company, self.from_date, self.to_date)

		by_emirate = get_standard_rated_by_emirate(
			self.company, self.from_date, self.to_date, rows=sales_rows
		)
		sales = get_sales_boxes(self.company, self.from_date, self.to_date, rows=sales_rows)

		taxable, exempt = get_period_supplies(sales_rows)
		recovery_ratio = get_recovery_ratio(taxable, exempt)
		purchases = get_purchase_boxes(
			self.company, self.from_date, self.to_date, rows=purchase_rows, recovery_ratio=recovery_ratio
		)
		adjustments = get_adjustments(
			get_return_companies(self.company), self.from_date, self.to_date, recovery_ratio
		)

		margin = get_margin_scheme(sales_rows)
		self.profit_margin_scheme_applied = int(margin["applied"])
		if margin["applied"]:
			purchases["standard_rated_expenses"]["amount"] += margin["purchase_price"]

		box_rows = list(_build_box_rows(by_emirate, sales, purchases, adjustments))

		self.recovery_ratio = recovery_ratio
		self.taxable_supplies_value = taxable
		self.exempt_supplies_value = exempt
		self.apportionment_recorded = 1
		self.residual_input_vat = purchases["residual_input_vat"] + adjustments["residual_input_vat"]
		self.residual_recoverable_vat = (
			purchases["residual_recoverable_vat"] + adjustments["residual_recoverable_vat"]
		)

		self.boxes = []
		for box_code, description, box in box_rows:
			self.append("boxes", {"box_code": box_code, "description": description, **box})

		totals = {code: box for code, _description, box in box_rows}
		sales_totals = totals[BOX_SALES_TOTALS]
		expense_totals = totals[BOX_EXPENSE_TOTALS]
		self.total_due_tax = get_total_due_tax(sales_totals)
		self.total_recoverable_tax = get_total_recoverable_tax(expense_totals)
		self.payable_tax = get_payable_tax(self.total_due_tax, self.total_recoverable_tax)

		self.generated_for_company = self.company
		self.generated_for_from_date = self.from_date
		self.generated_for_to_date = self.to_date

		self.save()

	@frappe.whitelist()
	def mark_as_filed(self):
		"""The only supported Draft to Filed transition. Needs generated, current boxes: filing a
		return that was never generated would lock in an all-zero return. The staleness check runs
		here, before status changes, so a stale save cannot persist an empty Filed return."""
		if self.status == "Filed":
			frappe.throw(_("This return has already been filed."))

		self.status = "Filed"
		try:
			self.validate_can_be_filed()
		except frappe.ValidationError:
			self.status = "Draft"
			raise

		self.save()

	@frappe.whitelist()
	def download_faf(self):
		"""The FTA Audit File (FAF) for this return's period."""
		from uae_compliance.uae_compliance.utils.faf import generate_faf

		frappe.has_permission(self.doctype, "read", doc=self, throw=True)
		frappe.response["filename"] = f"FAF-{self.name}.csv"
		frappe.response["filecontent"] = generate_faf(self.company, self.from_date, self.to_date)
		frappe.response["type"] = "download"


def _build_box_rows(by_emirate, sales, purchases, adjustments):
	"""Yield (box code, description, box) in the order of the VAT 201 form, with the totals rows
	(8 and 11) computed from the rows above them."""
	sales_boxes = []

	for emirate, box_code in EMIRATE_BOX_CODES.items():
		box = {**by_emirate[box_code], "adjustment": adjustments["by_emirate"][box_code]}
		sales_boxes.append(box)
		yield box_code, _("Standard rated supplies in {0}").format(_(emirate)), box

	rows = [
		(BOX_TOURIST_REFUNDS, _("Tax refunds provided to tourists"), sales["tourist_refunds"]),
		(
			BOX_REVERSE_CHARGE_SUPPLIES,
			_("Supplies subject to the reverse charge provisions"),
			purchases["reverse_charge_supplies"],
		),
		(BOX_ZERO_RATED, _("Zero rated supplies"), _amount_only(sales["zero_rated"])),
		(BOX_EXEMPT, _("Exempt supplies"), _amount_only(sales["exempt"])),
		(BOX_IMPORTS, _("Goods imported into the UAE"), purchases["imports"]),
		(BOX_IMPORT_ADJUSTMENTS, _("Adjustments to goods imported into the UAE"), adjustments["imports"]),
	]
	for code, description, box in rows:
		sales_boxes.append(box)
		yield code, description, box

	yield BOX_SALES_TOTALS, _("Totals"), get_sales_totals(sales_boxes)

	# VAT corrected in box 7 is recovered in box 10 to the extent it is recoverable.
	recovered = adjustments["imports_recoverable"]
	reverse_charge_expenses = {
		**purchases["reverse_charge_expenses"],
		"amount": purchases["reverse_charge_expenses"]["amount"] + recovered["amount"],
		"vat_amount": purchases["reverse_charge_expenses"]["vat_amount"] + recovered["vat_amount"],
	}
	expense_boxes = [
		{**purchases["standard_rated_expenses"], "adjustment": adjustments["expenses"]},
		reverse_charge_expenses,
	]
	yield BOX_STANDARD_RATED_EXPENSES, _("Standard rated expenses"), expense_boxes[0]
	yield (
		BOX_REVERSE_CHARGE_EXPENSES,
		_("Supplies subject to the reverse charge provisions"),
		expense_boxes[1],
	)
	yield BOX_EXPENSE_TOTALS, _("Totals"), get_expense_totals(expense_boxes)


def _amount_only(box: dict) -> dict:
	"""Boxes 4 and 5 have no VAT or adjustment columns."""
	return {"amount": box["amount"], "vat_amount": 0.0, "adjustment": 0.0}
