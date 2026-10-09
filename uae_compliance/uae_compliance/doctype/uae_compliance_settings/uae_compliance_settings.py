import re

import frappe
from frappe import _
from frappe.model.document import Document


class UAEComplianceSettings(Document):
	def validate(self):
		self.validate_unique_vat_account_per_company()
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

	def validate_patterns(self):
		for fieldname, label in (("trn_pattern", "TRN Pattern"), ("tin_pattern", "TIN Pattern")):
			pattern = self.get(fieldname)
			if not pattern:
				continue

			try:
				re.compile(pattern)
			except re.error as e:
				frappe.throw(
					_("{0} is not a valid regular expression: {1}").format(_(label), e),
					title=_("Invalid Pattern"),
				)

	def on_update(self):
		frappe.clear_document_cache(self.doctype, self.name)
