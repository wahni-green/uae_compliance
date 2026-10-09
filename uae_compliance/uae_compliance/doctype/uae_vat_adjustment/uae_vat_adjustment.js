frappe.ui.form.on("UAE VAT Adjustment", {
	sales_invoice(frm) {
		if (!frm.doc.sales_invoice) return;

		frappe.db.get_value("Sales Invoice", frm.doc.sales_invoice, "uae_emirate", (value) => {
			if (value && value.uae_emirate) frm.set_value("emirate", value.uae_emirate);
		});
	},

	calculate_apportionment(frm) {
		frm.call("calculate_apportionment").then(() => frm.refresh_fields());
	},
});
