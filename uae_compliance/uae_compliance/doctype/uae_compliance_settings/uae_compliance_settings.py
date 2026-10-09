import re

import frappe
from frappe import _
from frappe.model.document import Document


class UAEComplianceSettings(Document):
	def validate(self):
		self.validate_unique_vat_account_per_company()
		self.validate_account_ownership()
		self.validate_patterns()

	def validate_unique_vat_account_per_company(self):
		seen = set()
		for row in self.vat_accounts:
			if row.company in seen:
				frappe.throw(
					_("Company {0} has more than one row in VAT Accounts. Only one is allowed.").format(
						frappe.bold(row.company)
					),
					title=_("Duplicate VAT Account"),
				)

			seen.add(row.company)

	def validate_account_ownership(self):
		"""Each account must belong to its row's company and be a ledger (non-group) account."""
		for row in self.vat_accounts:
			for fieldname in ("output_vat_account", "input_vat_account", "excise_tax_account"):
				account = row.get(fieldname)
				if not account:
					continue

				company, is_group = frappe.db.get_value("Account", account, ["company", "is_group"])
				if company != row.company or is_group:
					frappe.throw(
						_("Row #{0}: {1} must be a non-group account of company {2}.").format(
							row.idx, frappe.bold(account), frappe.bold(row.company)
						),
						title=_("Invalid VAT Account"),
					)

	def validate_patterns(self):
		for fieldname, label in (("trn_pattern", "TRN Pattern"), ("tin_pattern", "TIN Pattern")):
			pattern = self.get(fieldname)
			if not pattern:
				continue

			try:
				re.compile(pattern)
			except re.error as e:
				frappe.throw(
					_("{0} is not a valid regular expression: {1}").format(_(label), str(e)),
					title=_("Invalid Pattern"),
				)

	def on_update(self):
		frappe.clear_document_cache(self.doctype, self.name)
