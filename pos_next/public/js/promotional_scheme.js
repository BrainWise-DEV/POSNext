// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

// Slab fields an Accumulative scheme does not use — its percentage comes from
// the per-scope rows instead.
const PN_SLAB_DISCOUNT_FIELDS = ["rate_or_discount", "rate", "discount_amount", "discount_percentage"];

const PN_SCOPE_TABLE_BY_APPLY_ON = {
	"Item Code": "items",
	"Item Group": "item_groups",
	Brand: "brands",
};

const PROMOTION_TYPE_GWP = "GWP";

const GWP_HIDDEN_PRODUCT_FIELDS = [
	"same_item",
	"free_item",
	"free_item_uom",
	"free_item_rate",
	"round_free_qty",
	"is_recursive",
	"recurse_for",
	"apply_recursion_over",
];

frappe.ui.form.on("Promotional Scheme", {
	refresh(frm) {
		pn_sync_min_max(frm);
		pn_sync_accumulative(frm);
		pn_toggle_gwp_fields(frm);
	},
	promotion_type(frm) {
		pn_toggle_gwp_fields(frm);
	},
	apply_on(frm) {
		pn_sync_accumulative(frm);
		pn_toggle_gwp_fields(frm);
	},
	mixed_conditions(frm) {
		pn_toggle_gwp_fields(frm);
	},
	items_add(frm) {
		pn_toggle_gwp_fields(frm);
	},
	items_remove(frm) {
		pn_toggle_gwp_fields(frm);
	},
	price_discount_slabs_remove(frm) {
		pn_sync_min_max(frm);
		pn_sync_accumulative(frm);
	},
});

frappe.ui.form.on("Promotional Scheme Price Discount", {
	apply_discount_on_price(frm) {
		pn_sync_min_max(frm);
		pn_sync_accumulative(frm);
	},
});

frappe.ui.form.on("Promotional Scheme Product Discount", {
	product_discount_slabs_add(frm) {
		pn_toggle_gwp_fields(frm);
	},
	form_rendered(frm, cdt, cdn) {
		pn_toggle_gwp_product_row(frm, cdt, cdn);
	},
});

function pn_toggle_gwp_fields(frm) {
	const is_gwp = frm.doc.promotion_type === PROMOTION_TYPE_GWP;

	frm.toggle_display("price_discount_slabs", !is_gwp);

	const product_grid = frm.fields_dict.product_discount_slabs?.grid;
	if (!product_grid) {
		return;
	}

	if (is_gwp) {
		pn_sync_gwp_mixed_conditions(frm);
	}

	(frm.doc.product_discount_slabs || []).forEach((row) => {
		pn_toggle_gwp_product_row(frm, "Promotional Scheme Product Discount", row.name);
	});

	if (is_gwp) {
		product_grid.refresh();
	}
}

function pn_toggle_gwp_product_row(frm, cdt, cdn) {
	const is_gwp = frm.doc.promotion_type === PROMOTION_TYPE_GWP;
	const grid = frm.fields_dict.product_discount_slabs?.grid;
	if (!grid || !locals[cdt]?.[cdn]) {
		return;
	}

	for (const fieldname of GWP_HIDDEN_PRODUCT_FIELDS) {
		grid.toggle_display(fieldname, !is_gwp, cdn);
	}
	grid.toggle_display("gwp_paid_qty_basis", is_gwp, cdn);
	grid.toggle_display("free_qty", true, cdn);
}

function pn_scheme_aggregates_gwp(frm) {
	return (
		frm.doc.apply_on === "Item Group" ||
		(frm.doc.apply_on === "Item Code" && (frm.doc.items || []).length > 1)
	);
}

function pn_sync_gwp_mixed_conditions(frm) {
	if (!pn_scheme_aggregates_gwp(frm)) {
		return;
	}
	if (!frm.doc.mixed_conditions) {
		frm.set_value("mixed_conditions", 1);
	}
}

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

/**
 * Accumulative schemes take their percentage from the per-scope rows.
 *
 * The price discount slab itself stays visible — ERPNext generates no Pricing
 * Rule without one, and the slab is where the mode, the cap and Min Scopes
 * Required live. Only its discount-value fields are hidden, and the product
 * (free item) slabs go away since an Item Level Discount cannot grant them.
 */
function pn_sync_accumulative(frm) {
	const slabs = frm.doc.price_discount_slabs || [];
	const is_accumulative = slabs.some((row) => row.apply_discount_on_price === "Accumulative");

	if (is_accumulative) {
		for (const row of slabs) {
			if (row.apply_discount_on_price !== "Accumulative") continue;
			// ERPNext needs a rate_or_discount to generate a Price rule at all.
			if (row.rate_or_discount !== "Discount Percentage") {
				frappe.model.set_value(row.doctype, row.name, "rate_or_discount", "Discount Percentage");
			}
			for (const fieldname of ["rate", "discount_amount", "discount_percentage"]) {
				if (row[fieldname]) {
					frappe.model.set_value(row.doctype, row.name, fieldname, 0);
				}
			}
		}
		if (!frm.doc.mixed_conditions) {
			frm.set_value("mixed_conditions", 1);
		}
	}

	const slab_grid = frm.fields_dict.price_discount_slabs?.grid;
	if (slab_grid) {
		for (const fieldname of PN_SLAB_DISCOUNT_FIELDS) {
			slab_grid.update_docfield_property(fieldname, "hidden", is_accumulative ? 1 : 0);
			slab_grid.update_docfield_property(fieldname, "in_list_view", is_accumulative ? 0 : 1);
		}
	}

	// Free items and Accumulative are mutually exclusive.
	frm.set_df_property("product_discount_slabs", "hidden", is_accumulative ? 1 : 0);

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
