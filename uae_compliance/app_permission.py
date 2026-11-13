import frappe

ALLOWED_ROLES = {"Accounts Manager", "Accounts User", "System Manager"}


def has_app_permission():
	return bool(ALLOWED_ROLES & set(frappe.get_roles()))
