import frappe
from frappe import _

from uae_compliance.uae_compliance.utils.trn import validate_tin, validate_trn

# The form enforces these with mandatory_depends_on; this covers imports and the API.
CONDITIONAL_REGISTRATION_FIELDS = (
	("uae_licence_authority", "Trade License", "Licence Issuing Authority"),
	("uae_passport_country", "Passport", "Passport Issuing Country"),
)


def validate_trn_and_tin(doc, method=None):
	doc.uae_trn = validate_trn(doc.uae_trn, label=f"{doc.doctype} TRN")
	doc.uae_tin = validate_tin(doc.uae_tin, label=f"{doc.doctype} TIN")
	validate_legal_registration(doc)


def validate_legal_registration(doc) -> None:
	if doc.get("uae_legal_registration_id") and not doc.get("uae_legal_registration_type"):
		frappe.throw(
			_("Set the Legal Registration Type: a Legal Registration ID is entered."),
			title=_("Legal Registration"),
		)

	for fieldname, registration_type, label in CONDITIONAL_REGISTRATION_FIELDS:
		if doc.get("uae_legal_registration_type") == registration_type and not doc.get(fieldname):
			frappe.throw(
				_("Set the {0}: the Legal Registration Type is {1}.").format(label, registration_type),
				title=_("Legal Registration"),
			)
