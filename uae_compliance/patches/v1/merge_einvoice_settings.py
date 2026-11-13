import frappe

OLD = "UAE E-Invoice Settings"
NEW = "UAE Compliance Settings"
CHILD = "UAE E-Invoice Company Setting"
# The value of each field that was never saved: the default of the old doctype.
FIELDS = {
	"retry_limit": 5,
	"block_cancellation_after_attempt": 0,
	"require_hsn_sac_code": 1,
	"exclude_intra_vat_group": 0,
	"intra_group_grace_end": None,
}


def execute():
	"""UAE E-Invoice Settings is part of UAE Compliance Settings: move its values and company rows,
	then remove the old doctype."""
	if not frappe.db.exists("DocType", OLD):
		return

	values = frappe.db.get_singles_dict(OLD)
	for fieldname, default in FIELDS.items():
		frappe.db.set_single_value(NEW, fieldname, values.get(fieldname, default))

	# The rows keep their names, so a stored client secret still belongs to its row.
	frappe.db.set_value(
		CHILD,
		{"parent": OLD, "parenttype": OLD},
		{"parent": NEW, "parenttype": NEW},
		update_modified=False,
	)

	frappe.delete_doc("DocType", OLD, force=True, ignore_missing=True)
	frappe.clear_document_cache(NEW, NEW)
