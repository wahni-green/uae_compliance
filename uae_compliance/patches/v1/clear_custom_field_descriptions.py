import frappe

from uae_compliance.uae_compliance.constants import MODULE


def execute() -> None:
	"""Custom fields no longer carry descriptions; clear any set by earlier versions."""
	for name in frappe.get_all(
		"Custom Field", filters={"module": MODULE, "description": ["is", "set"]}, pluck="name"
	):
		frappe.db.set_value("Custom Field", name, "description", None, update_modified=False)
