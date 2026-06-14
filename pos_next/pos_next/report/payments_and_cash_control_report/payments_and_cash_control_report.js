// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

frappe.query_reports["Payments and Cash Control Report"] = {
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
			"fieldname": "cashier",
			"label": __("Cashier"),
			"fieldtype": "Link",
			"options": "User"
		},
		{
			"fieldname": "mode_of_payment",
			"label": __("Mode of Payment"),
			"fieldtype": "Link",
			"options": "Mode of Payment"
		}
	]
};
