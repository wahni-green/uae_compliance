import json
import re

import frappe
from frappe import _
from frappe.model.document import Document

from uae_compliance.uae_compliance.einvoice.registry import get_provider_class
from uae_compliance.uae_compliance.utils.rounding import warn_if_not_commercial_rounding


class UAEComplianceSettings(Document):
	def validate(self):
		self.validate_unique_vat_account_per_company()
		self.validate_account_ownership()
		self.validate_distinct_vat_accounts()
		self.validate_patterns()
		self.validate_einvoice_companies()

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

	def validate_distinct_vat_accounts(self):
		"""The VAT return and every VAT check tell the accounts apart, so one account for two of them
		would count each tax row as both."""
		for row in self.vat_accounts:
			accounts = [
				row.get(fieldname)
				for fieldname in ("output_vat_account", "input_vat_account", "excise_tax_account")
			]
			accounts = [account for account in accounts if account]
			if len(accounts) != len(set(accounts)):
				frappe.throw(
					_(
						"Row #{0}: the Output VAT, Input VAT and Excise Tax accounts must all be different."
					).format(row.idx),
					title=_("Same VAT Account"),
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

	def validate_einvoice_companies(self):
		seen = set()
		for row in self.companies:
			if row.company in seen:
				frappe.throw(
					_("Company {0} has more than one row in E-Invoice Companies.").format(
						frappe.bold(row.company)
					),
					title=_("Duplicate Company"),
				)

			seen.add(row.company)
			self.validate_einvoice_row(row)

		if any(row.enabled for row in self.companies):
			warn_if_not_commercial_rounding()

	def validate_einvoice_row(self, row):
		provider = get_provider_class(row.provider)

		if row.extra_config:
			try:
				extra = json.loads(row.extra_config)
			except ValueError as e:
				frappe.throw(
					_("Row #{0}: the extra configuration is not valid JSON: {1}").format(row.idx, str(e))
				)

			if not isinstance(extra, dict):
				frappe.throw(_("Row #{0}: the extra configuration must be a JSON object.").format(row.idx))

		if not row.enabled:
			return

		missing = [
			frappe.unscrub(field)
			for field in provider.required_settings
			if not (row.get(field) or (field == "client_secret" and self.has_secret(row)))
		]
		if missing:
			frappe.throw(
				_("Row #{0}: {1} needs {2}.").format(row.idx, row.provider, ", ".join(missing)),
				title=_("Missing Provider Settings"),
			)

	def has_secret(self, row) -> bool:
		from frappe.utils.password import get_decrypted_password

		if row.client_secret and row.client_secret != "*" * len(row.client_secret):
			return True

		return bool(get_decrypted_password(row.doctype, row.name, "client_secret", raise_exception=False))

	def on_update(self):
		frappe.clear_document_cache(self.doctype, self.name)
