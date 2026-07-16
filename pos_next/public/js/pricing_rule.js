// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt


frappe.ui.form.on("Pricing Rule", {
	refresh(frm) {
		pn_toggle_min_max(frm);
	},
	apply_discount_on_price(frm) {
		pn_toggle_min_max(frm);
	},
});

function pn_toggle_min_max(frm) {
	const is_min_max = ["Min", "Max"].includes(frm.doc.apply_discount_on_price);
	if (is_min_max && !frm.doc.mixed_conditions) {
		frm.set_value("mixed_conditions", 1);
	}
	frm.set_df_property("mixed_conditions", "read_only", is_min_max ? 1 : 0);
	frm.set_df_property(
		"mixed_conditions",
		"description",
		is_min_max
			? __(
					"Automatically enabled and locked because <b>Apply Discount On</b> is set to Min/Max. " +
						"A cheapest/most-expensive-item discount must evaluate all document items together " +
						"(not line by line), which requires Mixed Conditions. Clear <b>Apply Discount On</b> to edit this."
				)
			: ""
	);
}
