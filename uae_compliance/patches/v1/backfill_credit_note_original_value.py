import frappe
from frappe.utils import flt

from uae_compliance.uae_compliance.utils.print_data import get_value_before_credit_note


def execute() -> None:
	"""Fill the stored starting value of credit notes submitted before it was stored, in order of
	issue (posting date and time, then creation). Best effort: the true submission order of such
	credit notes was never recorded."""
	if not frappe.db.has_column("Sales Invoice", "uae_credit_note_original_value"):
		return

	credit_notes = frappe.get_all(
		"Sales Invoice",
		filters={"is_return": 1, "docstatus": 1, "return_against": ["is", "set"]},
		fields=[
			"name",
			"return_against",
			"posting_date",
			"posting_time",
			"creation",
			"uae_credit_note_original_value",
		],
		order_by="posting_date, posting_time, creation",
	)
	for note in credit_notes:
		if flt(note.uae_credit_note_original_value):
			continue

		value = get_value_before_credit_note(
			frappe._dict(name=note.name, return_against=note.return_against),
			issued_before=(str(note.posting_date), str(note.posting_time), str(note.creation)),
		)
		frappe.db.set_value(
			"Sales Invoice", note.name, "uae_credit_note_original_value", value, update_modified=False
		)
