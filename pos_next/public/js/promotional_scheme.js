// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

// Frappe concatenates every app's doctype_js into one Function. Yield to
// posnext_promotions when it is installed so the two copies do not redeclare
// const or double-bind handlers.
(function () {
	if (frappe.boot && frappe.boot.posnext_promotions) {
		return;
	}

	frappe.ui.form.on("Promotional Scheme", {
		refresh(frm) {
			pn_sync_min_max(frm);
		},
		price_discount_slabs_remove(frm) {
			pn_sync_min_max(frm);
		},
	});

	frappe.ui.form.on("Promotional Scheme Price Discount", {
		apply_discount_on_price(frm) {
			pn_sync_min_max(frm);
		},
	});

	function pn_sync_min_max(frm) {
		const has_min_max = (frm.doc.price_discount_slabs || []).some((row) =>
			["Min", "Max"].includes(row.apply_discount_on_price)
		);
		if (has_min_max && !frm.doc.mixed_conditions) {
			frm.set_value("mixed_conditions", 1);
		}
		frm.set_df_property("mixed_conditions", "read_only", has_min_max ? 1 : 0);
		frm.set_df_property(
			"mixed_conditions",
			"description",
			has_min_max
				? __(
						"Automatically enabled and locked because a price discount row uses a Min/Max discount. " +
							"A cheapest/most-expensive-item discount must evaluate all document items together " +
							"which requires Mixed Conditions. Remove the Min/Max rows to edit this."
					)
				: ""
		);
	}
})();
