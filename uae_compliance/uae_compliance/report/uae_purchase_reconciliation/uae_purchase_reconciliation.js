frappe.query_reports["UAE Purchase Reconciliation"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Matched", "Mismatch", "Only Received", "Only in Books", "Ignored"],
		},
	],

	get_datatable_options(options) {
		return Object.assign(options, { checkboxColumn: true });
	},

	onload(report) {
		const call = (method, args, done) =>
			frappe.call({ method: `uae_compliance.uae_compliance.einvoice.reconciliation.${method}`, args, callback: done });

		const selected = () =>
			report.datatable.rowmanager
				.getCheckedRows()
				.map((i) => report.data[i])
				.filter(Boolean);

		const refresh = () => report.refresh();

		report.page.add_inner_button(__("Run Matching"), () => {
			const filters = report.get_values();
			call("run_matching", { company: filters.company, from_date: filters.from_date, to_date: filters.to_date }, (r) => {
				frappe.show_alert({ message: __("{0} matched", [r.message.matched]), indicator: "green" });
				refresh();
			});
		});

		report.page.add_inner_button(__("Link"), () => {
			const rows = selected();
			let log, invoice;
			if (rows.length === 1 && rows[0].received && rows[0].invoice) {
				({ received: log, invoice } = rows[0]);
			} else if (rows.length === 2) {
				log = (rows.find((r) => r.received && !r.invoice) || {}).received;
				invoice = (rows.find((r) => r.invoice && !r.received) || {}).invoice;
			}

			if (!log || !invoice) {
				frappe.msgprint(
					__("Select one Mismatch row, or one Only Received row and one Only in Books row.")
				);
				return;
			}

			call("link_documents", { log, invoice }, refresh);
		}, __("Actions"));

		report.page.add_inner_button(__("Unlink"), () => {
			const logs = selected().filter((r) => r.received && r.invoice).map((r) => r.received);
			if (!logs.length) return frappe.msgprint(__("Select linked rows."));
			call("unlink_documents", { logs }, refresh);
		}, __("Actions"));

		report.page.add_inner_button(__("Ignore"), () => {
			const rows = selected();
			const logs = rows.filter((r) => r.received && !r.invoice).map((r) => r.received);
			const invoices = rows.filter((r) => r.invoice && !r.received).map((r) => r.invoice);
			if (!logs.length && !invoices.length) return frappe.msgprint(__("Select Only Received or Only in Books rows."));
			call("ignore_documents", { logs, invoices }, refresh);
		}, __("Actions"));

		report.page.add_inner_button(__("Restore Ignored"), () => {
			const rows = selected();
			const logs = rows.filter((r) => r.received && !r.invoice).map((r) => r.received);
			const invoices = rows.filter((r) => r.invoice && !r.received).map((r) => r.invoice);
			if (!logs.length && !invoices.length) return frappe.msgprint(__("Select ignored rows."));
			call("restore_documents", { logs, invoices }, refresh);
		}, __("Actions"));
	},
};
