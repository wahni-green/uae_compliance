import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_years, flt, getdate

from uae_compliance.uae_compliance.constants import (
	ADJUSTMENT_CAPITAL_ASSETS,
	CAPITAL_ASSET_THRESHOLD,
	CAPITAL_ASSET_YEARS,
)


class UAECapitalAsset(Document):
	def validate(self):
		if flt(self.cost) < CAPITAL_ASSET_THRESHOLD:
			frappe.throw(
				_("The capital assets scheme applies to assets costing {0} or more excluding VAT.").format(
					frappe.format(CAPITAL_ASSET_THRESHOLD, {"fieldtype": "Currency"})
				),
				title=_("Below the Threshold"),
			)

		self.adjustment_years = CAPITAL_ASSET_YEARS[self.asset_type]
		self.annual_input_vat = flt(flt(self.input_vat) / self.adjustment_years, 2)

		self.build_schedule()
		self.calculate_adjustments()

	def build_schedule(self):
		"""One row per year of the adjustment period, counted from first use. Rows already there keep
		what the user entered."""
		existing = {row.adjustment_year: row for row in self.adjustments}
		self.adjustments = []
		for year in range(1, self.adjustment_years + 1):
			row = existing.get(year)
			values = {
				"adjustment_year": year,
				"tax_year_end": add_years(getdate(self.first_use_date), year),
				"recoverable_percentage": (
					row.recoverable_percentage
					if row and row.recoverable_percentage is not None
					else self.initial_recoverable_percentage
				),
				"adjustment_date": row.adjustment_date if row else None,
				"vat_adjustment": row.vat_adjustment if row else None,
			}
			self.append("adjustments", values)

	def calculate_adjustments(self):
		"""Each year adjusts 1/10 (buildings) or 1/5 (other assets) of the input VAT by the change in
		the recoverable percentage since the asset was first used (ER Art 57)."""
		for row in self.adjustments:
			change = flt(row.recoverable_percentage) - flt(self.initial_recoverable_percentage)
			row.adjustment_vat = flt(flt(self.annual_input_vat) * change / 100, 2)

	@frappe.whitelist()
	def create_adjustment(self, row_name: str):
		"""A draft UAE VAT Adjustment for one year, to be reviewed and submitted."""
		row = next((row for row in self.adjustments if row.name == row_name), None)
		if not row:
			frappe.throw(_("Adjustment row not found."))

		if row.vat_adjustment:
			frappe.throw(_("An adjustment was already created for year {0}.").format(row.adjustment_year))

		if not flt(row.adjustment_vat):
			frappe.throw(_("Year {0} has no adjustment to report.").format(row.adjustment_year))

		if not row.adjustment_date:
			frappe.throw(_("Set the period the adjustment is reported in first."))

		adjustment = frappe.get_doc(
			{
				"doctype": "UAE VAT Adjustment",
				"company": self.company,
				"adjustment_type": ADJUSTMENT_CAPITAL_ASSETS,
				"posting_date": row.adjustment_date,
				"vat_amount": row.adjustment_vat,
				"remarks": _("{0}, year {1} of {2}").format(
					self.asset_name, row.adjustment_year, self.adjustment_years
				),
			}
		).insert()

		row.vat_adjustment = adjustment.name
		self.save()
		return adjustment.name
