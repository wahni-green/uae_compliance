frappe.query_reports["UAE E-Invoice Status"] = {
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
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: [
				"",
				"Not Sent",
				"Pending",
				"Generated",
				"Invalid",
				"Submitted",
				"Delivered",
				"Cleared",
				"Rejected",
				"Failed",
			],
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname !== "status" || !data) return value;

		const color = {
			Cleared: "green",
			Delivered: "blue",
			Submitted: "blue",
			Pending: "orange",
			Generated: "orange",
			Invalid: "red",
			Rejected: "red",
			Failed: "red",
		}[data.status];
		return color ? `<span class="indicator-pill ${color}">${value}</span>` : value;
	},
};
