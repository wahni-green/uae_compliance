// What each provider reads from the Extra Configuration, with placeholder values to replace. Keys that
// would change behaviour when left as a sample (the ClearTax trn and branch) are left out.
const EXTRA_CONFIG_TEMPLATES = {
	ClearTax: { timeout: 60, inbound_days: 30 },
	Microvista: { client_code: "CLIENT_CODE", version: "v1", timeout: 60, inbound_days: 30 },
	Mock: { behavior: "clear" },
};

frappe.ui.form.on("UAE E-Invoice Company Setting", {
	provider(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const template = EXTRA_CONFIG_TEMPLATES[row.provider];

		// Never overwrite what has already been typed in.
		if (template && !row.extra_config) {
			frappe.model.set_value(cdt, cdn, "extra_config", JSON.stringify(template, null, 2));
		}
	},
});
