frappe.ui.form.on("Price Group", {
	refresh(frm) {
		// Filter warehouse by company of each child row
		frm.fields_dict.outlets.grid.get_field("warehouse").get_query = (doc, cdt, cdn) => {
			const row = locals[cdt][cdn]
			return {
				filters: {
					company: row.company || "",
					is_group: 0,
				},
			}
		}
	},
})

frappe.ui.form.on("Price Group Outlet", {
	company(frm, cdt, cdn) {
		// Clear dependent fields when company changes
		frappe.model.set_value(cdt, cdn, "warehouse", "")
		frappe.model.set_value(cdt, cdn, "pos_profile", "")
		frappe.model.set_value(cdt, cdn, "status", "")
	},
})
