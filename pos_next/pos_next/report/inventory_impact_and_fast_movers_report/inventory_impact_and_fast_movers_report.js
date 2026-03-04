// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

frappe.query_reports["Inventory Impact and Fast Movers Report"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_days(frappe.datetime.get_today(), -30),
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
			"fieldname": "shift",
			"label": __("Shift"),
			"fieldtype": "Link",
			"options": "POS Closing Shift"
		},
		{
			"fieldname": "pos_profile",
			"label": __("POS Profile"),
			"fieldtype": "Link",
			"options": "POS Profile"
		},
		{
			"fieldname": "item_group",
			"label": __("Item Group"),
			"fieldtype": "Link",
			"options": "Item Group"
		}
	],
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname == "stock_status") {
			// Add color based on status
			if (value && value.includes("Out of Stock")) {
				value = "<span style='color: red'>" + value + "</span>";
			} else if (value && value.includes("Critical")) {
				value = "<span style='color: orange'>" + value + "</span>";
			} else if (value && value.includes("Low")) {
				value = "<span style='color: #FFA500'>" + value + "</span>";
			} else if (value && value.includes("Good")) {
				value = "<span style='color: green'>" + value + "</span>";
			}
		}

		return value;
	}
};
