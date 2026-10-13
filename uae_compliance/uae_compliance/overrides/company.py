from uae_compliance.uae_compliance.setup import hide_erpnext_uae_fields
from uae_compliance.uae_compliance.utils.company import UAE
from uae_compliance.uae_compliance.utils.trn import validate_tin, validate_trn


UAE_FIELDS = (
	"uae_company_name_in_arabic",
	"uae_tax_group",
	"uae_trn",
	"uae_tin",
	"uae_legal_registration_type",
	"uae_legal_registration_id",
	"uae_licence_authority",
	"uae_passport_country",
)


def validate(doc, method=None):
	if doc.country != UAE:
		# The tab is hidden for other countries, so nothing entered earlier should linger on it.
		for fieldname in UAE_FIELDS:
			doc.set(fieldname, None)
		return

	doc.uae_trn = validate_trn(doc.uae_trn, label="Company TRN")
	doc.uae_tin = validate_tin(doc.uae_tin, label="Company TIN")


def hide_erpnext_regional_fields(doc, method=None):
	"""ERPNext creates its own UAE custom fields when a UAE company is created, which happens after
	this app is installed. Hide them again at that point (idempotent)."""
	# Check the document being saved, not the cached Company value, which can be stale here.
	if doc.country == UAE:
		hide_erpnext_uae_fields()
