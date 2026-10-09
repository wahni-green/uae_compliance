import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from uae_compliance.uae_compliance.utils.trn import validate_trn


class UAETRN(Document):
	def before_naming(self):
		# Runs before the "field:trn" autoname rule copies `trn` into `name`, so the normalized
		# value becomes the document name.
		self.trn = validate_trn(self.trn, label="TRN")

	def validate(self):
		self.trn = validate_trn(self.trn, label="TRN")

		if self.is_new():
			self.last_validated_on = now_datetime()
			return

		# The name is the TRN, so the two must never diverge: changing a TRN means renaming.
		if self.trn != self.name:
			frappe.throw(
				_("The TRN cannot be changed after creation. Rename the record instead."),
				title=_("TRN Locked"),
			)

	def before_rename(self, old, new, merge=False):
		return validate_trn(new, label="TRN")
