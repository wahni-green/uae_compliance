from frappe.custom.doctype.custom_field.custom_field import create_custom_fields as _create_custom_fields

from uae_compliance.uae_compliance.constants.custom_fields import CUSTOM_FIELDS


def create_custom_fields() -> None:
	if CUSTOM_FIELDS:
		_create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
