import frappe

OLD_FIELDS = ("uae_hs_code", "uae_sac_code")


def execute():
	"""One HSN/SAC Code on an Item replaces the HS code and the service accounting code. A code
	already entered moves over, and the old fields are removed."""
	for fieldname in OLD_FIELDS:
		if frappe.db.has_column("Item", fieldname):
			frappe.db.sql(
				f"update `tabItem` set uae_hsn_sac_code = `{fieldname}` "
				f"where ifnull(uae_hsn_sac_code, '') = '' and ifnull(`{fieldname}`, '') != ''"
			)

		frappe.delete_doc("Custom Field", f"Item-{fieldname}", ignore_missing=True, force=True)
