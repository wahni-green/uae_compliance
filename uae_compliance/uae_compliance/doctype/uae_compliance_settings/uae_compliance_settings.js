frappe.ui.form.on("UAE Compliance Settings", {
	setup(frm) {
		["output_vat_account", "input_vat_account", "excise_tax_account"].forEach((fieldname) => {
			frm.set_query(fieldname, "vat_accounts", (doc, cdt, cdn) => {
				const row = locals[cdt][cdn];
				return { filters: { company: row.company, is_group: 0 } };
			});
		});
	},
});
