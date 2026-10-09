frappe.ui.form.on("UAE Capital Asset", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Create Adjustment"), () => {
			const row = (frm.fields_dict.adjustments.grid.get_selected_children() || [])[0];
			if (!row) {
				frappe.msgprint(__("Select a yearly adjustment row first."));
				return;
			}

			frm.call("create_adjustment", { row_name: row.name }).then(() => frm.reload_doc());
		});
	},
});
