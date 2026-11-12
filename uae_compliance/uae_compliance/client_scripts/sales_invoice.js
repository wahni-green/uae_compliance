const EINVOICE_STATUS_COLORS = {
	Cleared: "green",
	Delivered: "blue",
	Submitted: "blue",
	Generated: "blue",
	Pending: "orange",
	Invalid: "red",
	Rejected: "red",
	Failed: "red",
};

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		show_einvoice_status(frm);
	},
});

function show_einvoice_status(frm) {
	frm.dashboard.clear_headline();

	const status = frm.doc.uae_einvoice_status;
	if (frm.is_new() || !status) return;

	const color = EINVOICE_STATUS_COLORS[status] || "gray";
	frm.dashboard.set_headline_alert(
		`${__("E-Invoice Status")}: <strong>${__(status)}</strong>`,
		color
	);
}
