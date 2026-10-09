import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields as _create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from uae_compliance.uae_compliance.constants import DEFAULT_TIN_PATTERN, DEFAULT_TRN_PATTERN
from uae_compliance.uae_compliance.constants.custom_fields import CUSTOM_FIELDS
from uae_compliance.uae_compliance.constants.designated_zones import DESIGNATED_ZONES
from uae_compliance.uae_compliance.constants.erpnext_uae_fields import ERPNEXT_UAE_FIELDS
from uae_compliance.uae_compliance.constants.excise_rates import EFFECTIVE_FROM, EXCISE_RATES


def create_custom_fields() -> None:
	_create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)


def create_designated_zones() -> None:
	# Insert-only: an admin may have edited a zone, so existing rows are never overwritten. A
	# correction to the seed list needs an explicit dated patch.
	for zone in DESIGNATED_ZONES:
		if frappe.db.exists("UAE Designated Zone", zone["zone_name"]):
			continue

		frappe.get_doc({"doctype": "UAE Designated Zone", **zone}).insert(ignore_permissions=True)


def create_excise_rates() -> None:
	# Insert-only, like the designated zones: an admin may have edited a rate.
	for rate in EXCISE_RATES:
		if frappe.db.exists("UAE Excise Rate", rate["category"]):
			continue

		frappe.get_doc(
			{"doctype": "UAE Excise Rate", "effective_from": EFFECTIVE_FROM, "is_active": 1, **rate}
		).insert(ignore_permissions=True)


def set_default_settings() -> None:
	# A Single's field-level `default` only applies to a document that was never persisted, so
	# explicitly fill any blank value (never overwriting an admin's value).
	defaults = {
		"settings_currency": "AED",
		"simplified_tax_invoice_threshold": 10000,
		"mandatory_registration_threshold": 375000,
		"voluntary_registration_threshold": 187500,
		"trn_pattern": DEFAULT_TRN_PATTERN,
		"tin_pattern": DEFAULT_TIN_PATTERN,
	}
	for fieldname, value in defaults.items():
		if not frappe.db.get_single_value("UAE Compliance Settings", fieldname):
			frappe.db.set_single_value("UAE Compliance Settings", fieldname, value)


def hide_erpnext_uae_fields() -> None:
	"""Hide ERPNext's own UAE localization fields (replaced by this app) with Property Setters.
	Idempotent. Property Setters apply site-wide, not per company. Fields are hidden, never
	deleted, so existing data is kept and the change can be reverted by removing the setters."""
	for doctype, fieldnames in ERPNEXT_UAE_FIELDS.items():
		for fieldname in fieldnames:
			if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname}):
				continue

			if frappe.db.exists(
				"Property Setter",
				{
					"doc_type": doctype,
					"field_name": fieldname,
					"property": "hidden",
					"value": "1",
				},
			):
				continue

			make_property_setter(
				doctype,
				fieldname,
				"hidden",
				1,
				"Check",
				validate_fields_for_doctype=False,
			)
