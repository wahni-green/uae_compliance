import frappe

from uae_compliance.uae_compliance.constants import DEFAULT_TRN_PATTERN, LEGACY_TRN_PATTERN


def execute() -> None:
	"""The default TRN pattern now follows the PINT AE specification (15 digits, starting with 1 and
	ending with 03). Sites still on the earlier default move to it; a pattern an admin chose is kept."""
	current = frappe.db.get_single_value("UAE Compliance Settings", "trn_pattern")
	if current == LEGACY_TRN_PATTERN:
		frappe.db.set_single_value("UAE Compliance Settings", "trn_pattern", DEFAULT_TRN_PATTERN)
		frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")
