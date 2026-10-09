from uae_compliance.uae_compliance.setup import hide_erpnext_uae_fields
from uae_compliance.uae_compliance.utils.company import is_uae_company
from uae_compliance.uae_compliance.utils.trn import validate_tin, validate_trn


def validate(doc, method=None):
	doc.uae_trn = validate_trn(doc.uae_trn, label="Company TRN")
	doc.uae_tin = validate_tin(doc.uae_tin, label="Company TIN")


def hide_erpnext_regional_fields(doc, method=None):
	"""ERPNext creates its own UAE custom fields when a UAE company is created, which happens after
	this app is installed. Hide them again at that point (idempotent)."""
	if is_uae_company(doc.name):
		hide_erpnext_uae_fields()
