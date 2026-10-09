frappe.ui.form.on("UAE E-Invoice Log", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.direction !== "Outbound") return;

		if (["Invalid", "Rejected", "Failed", "Generated"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Retry"), () => {
				frm.call("retry").then(() => frm.reload_doc());
			});
		}

		if (["Submitted", "Delivered"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Check Status"), () => {
				frm.call("check_status").then(() => frm.reload_doc());
			});
		}
	},
});
