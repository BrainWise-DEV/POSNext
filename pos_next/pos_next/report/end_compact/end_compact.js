frappe.query_reports["End Compact"] = {
	"filters": [
		{
			"fieldname": "pos_profile",
			"label": __("POS Profile Name"),
			"fieldtype": "Link",
			"options": "POS Profile",
			"default": ""
		}
	],
	"formatter": function (value, row, column, data, default_formatter) {
		if (typeof value === 'string' && value.includes("<strong>")) {
			return value;
		}
		
		let original_value = value;
		value = default_formatter(value, row, column, data);
		
		if (data) {
			if (data.mode_of_payment === " ") {
				if (column.fieldname != "mode_of_payment" && (value === "₹ 0.00" || value === "0" || original_value === null)) {
					return "";
				}
			}
			
			if (data._is_category_row && data._percentage_columns && data._percentage_columns.includes(column.fieldname)) {
				if (original_value !== undefined && original_value !== null && original_value !== "") {
					return flt(original_value).toFixed(2) + " %";
				} else {
					return "";
				}
			}

			if (data._is_category_row && data._category_columns && !data._category_columns.includes(column.fieldname)) {
				return "";
			}
		}
		
		return value;
	}
};
