// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

frappe.ui.form.on("Customer", {
	refresh(frm) {
		frm.set_query("custom_district", () => {
			return {
				filters: {
					governorate: frm.doc.custom_governorate || "",
				},
			}
		})
	},

	custom_governorate(frm) {
		if (frm.doc.custom_district) {
			frm.set_value("custom_district", null)
		}
	},
})
