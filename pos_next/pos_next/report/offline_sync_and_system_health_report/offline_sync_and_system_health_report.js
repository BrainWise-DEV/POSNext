// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

frappe.query_reports["Offline Sync and System Health Report"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_days(frappe.datetime.get_today(), -7),
			"reqd": 0
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 0
		},
		{
			"fieldname": "pos_profile",
			"label": __("POS Profile"),
			"fieldtype": "Link",
			"options": "POS Profile"
		},
		{
			"fieldname": "status",
			"label": __("Sync Status"),
			"fieldtype": "Select",
			"options": "\nPending\nSynced\nFailed",
			"default": ""
		},
		{
			"fieldname": "user",
			"label": __("User"),
			"fieldtype": "Link",
			"options": "User"
		}
	],
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname == "health_status") {
			// Color-code health status
			if (value && value.includes("Failed")) {
				value = "<span style='color: red; font-weight: bold'>" + value + "</span>";
			} else if (value && value.includes("Pending")) {
				value = "<span style='color: orange; font-weight: bold'>" + value + "</span>";
			} else if (value && value.includes("Delayed")) {
				value = "<span style='color: orange'>" + value + "</span>";
			} else if (value && value.includes("✅")) {
				value = "<span style='color: green'>" + value + "</span>";
			}
		}

		if (column.fieldname == "sync_delay_hours") {
			// Highlight delays over 1 hour
			if (data.sync_delay_hours > 1) {
				value = "<span style='color: orange; font-weight: bold'>" + value + "</span>";
			}
		}

		return value;
	}
};
