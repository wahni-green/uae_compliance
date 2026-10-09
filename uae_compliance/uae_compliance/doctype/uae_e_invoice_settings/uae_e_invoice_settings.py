import json

import frappe
from frappe import _
from frappe.model.document import Document

from uae_compliance.uae_compliance.einvoice.registry import get_provider_class


class UAEEInvoiceSettings(Document):
	def validate(self):
		seen = set()
		for row in self.companies:
			if row.company in seen:
				frappe.throw(
					_("Company {0} has more than one row.").format(frappe.bold(row.company)),
					title=_("Duplicate Company"),
				)

			seen.add(row.company)
			self.validate_row(row)

	def validate_row(self, row):
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
