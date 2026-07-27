// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

// Discount-value fields an Accumulative rule does not use. Its percentage comes
// from the per-scope rows instead, and the engine ignores these outright — see
// pos_next/overrides/pricing_rule.py#apply_price_discount_rule.
const PN_DISCOUNT_VALUE_FIELDS = [
	"price_or_product_discount",
	"rate_or_discount",
	"rate",
	"discount_amount",
	"discount_percentage",
];

const PN_SCOPE_TABLE_BY_APPLY_ON = {
	"Item Code": "items",
	"Item Group": "item_groups",
	Brand: "brands",
};

frappe.ui.form.on("Pricing Rule", {
	refresh(frm) {
		pn_toggle_min_max(frm);
		pn_toggle_accumulative(frm);
	},
	apply_discount_on_price(frm) {
		pn_toggle_min_max(frm);
		pn_toggle_accumulative(frm);
	},
	apply_on(frm) {
		pn_toggle_accumulative(frm);
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

/**
 * An Accumulative rule takes its percentage from the per-scope rows, so the
 * rule-level discount fields are hidden to stop them being filled in by mistake.
 *
 * `price_or_product_discount` is mandatory on the DocType, so it is pinned to
 * "Price" rather than merely hidden — a hidden-but-empty mandatory field blocks
 * the save.
 */
function pn_toggle_accumulative(frm) {
	const is_accumulative = frm.doc.apply_discount_on_price === "Accumulative";

	if (is_accumulative) {
		if (frm.doc.price_or_product_discount !== "Price") {
			frm.set_value("price_or_product_discount", "Price");
		}
		if (frm.doc.rate_or_discount !== "Discount Percentage") {
			frm.set_value("rate_or_discount", "Discount Percentage");
		}
		// Clear anything already typed so a stale value can't mislead on the form.
		for (const fieldname of ["rate", "discount_amount", "discount_percentage"]) {
			if (frm.doc[fieldname]) {
				frm.set_value(fieldname, 0);
			}
		}
		if (!frm.doc.mixed_conditions) {
			frm.set_value("mixed_conditions", 1);
		}
	}

	for (const fieldname of PN_DISCOUNT_VALUE_FIELDS) {
		frm.set_df_property(fieldname, "hidden", is_accumulative ? 1 : 0);
	}

	pn_toggle_scope_percentage(frm, is_accumulative);
}

/** Surface Discount % on the scope grid only where it means something. */
function pn_toggle_scope_percentage(frm, is_accumulative) {
	for (const table_field of Object.values(PN_SCOPE_TABLE_BY_APPLY_ON)) {
		const grid = frm.fields_dict[table_field]?.grid;
		if (!grid) continue;
		grid.update_docfield_property("pos_discount_percentage", "hidden", is_accumulative ? 0 : 1);
		grid.update_docfield_property(
			"pos_discount_percentage",
			"in_list_view",
			is_accumulative ? 1 : 0
		);
	}

	const active_table = PN_SCOPE_TABLE_BY_APPLY_ON[frm.doc.apply_on];
	if (!active_table || !frm.fields_dict[active_table]) return;

	frm.set_df_property(
		active_table,
		"description",
		is_accumulative
			? __(
					"Set <b>Discount %</b> on each row. Every row represented in the cart contributes " +
						"its percentage and the total applies to each eligible line, so a cart spanning " +
						"more rows earns a bigger discount on everything in it."
				)
			: ""
	);
}
