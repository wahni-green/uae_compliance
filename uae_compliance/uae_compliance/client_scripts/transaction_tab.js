// The UAE tab of Sales Order, Delivery Note and Sales Invoice, shown only for a UAE company.
for (const doctype of ["Sales Order", "Delivery Note", "Sales Invoice"]) {
	frappe.ui.form.on(doctype, {
		refresh: toggle_uae_tab,
		company: toggle_uae_tab,
	});
}

async function toggle_uae_tab(frm) {
	const company = frm.doc.company;
	const country = company ? await frappe.db.get_value("Company", company, "country") : null;

	// The company may have been changed while awaiting the server round-trip.
	if (company !== frm.doc.company) return;

	const is_uae = country?.message?.country === "United Arab Emirates";
	frm.set_df_property("uae_tab", "hidden", is_uae ? 0 : 1);
}
