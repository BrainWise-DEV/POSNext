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
const PROMOTION_TYPE_GIFT_POOL = "Gift Pool";

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
		pn_toggle_gift_pool_fields(frm);
	},
	promotion_type(frm) {
		pn_toggle_gwp_fields(frm);
		pn_toggle_gift_pool_fields(frm);
	},
	pos_is_accumulative(frm) {
		pn_sync_accumulative(frm);
	},
	apply_on(frm) {
		pn_sync_accumulative(frm);
		pn_toggle_gwp_fields(frm);
		pn_toggle_gift_pool_fields(frm);
	},
	toggle_reqd_apply_on(frm) {
		pn_unrequire_hidden_gift_pool_tables(frm);
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
	gift_pool_items_add(frm, cdt, cdn) {
		pn_default_gift_pool_free_qty(frm, cdt, cdn);
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

frappe.ui.form.on("POS Gift Pool Item", {
	item_group(frm, cdt, cdn) {
		const row = locals[cdt]?.[cdn];
		if (!row?.item_code || frm._pn_setting_gift_pool_rows) {
			return;
		}
		frappe.model.set_value(cdt, cdn, "item_code", "");
	},
	free_qty(frm, cdt, cdn) {
		pn_sync_gift_pool_free_qty(frm, cdt, cdn);
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

function pn_toggle_gift_pool_fields(frm) {
	const is_gift_pool = frm.doc.promotion_type === PROMOTION_TYPE_GIFT_POOL;

	if (is_gift_pool && frm.doc.apply_on !== "Item Group") {
		frm.set_value("apply_on", "Item Group");
	}
	if (is_gift_pool && frm.doc.pos_is_accumulative) {
		frm.set_value("pos_is_accumulative", 0);
	}
	if (is_gift_pool && !frm.doc.mixed_conditions) {
		frm.set_value("mixed_conditions", 1);
	}

	frm.toggle_display("gift_pool_items", is_gift_pool);
	// Gift Pool forces Apply On = Item Group, which would otherwise keep the
	// Item Groups table visible via depends_on. Hide it; unique groups are
	// synced from gift_pool_items on save.
	frm.set_df_property(
		"item_groups",
		"depends_on",
		is_gift_pool ? "eval:false" : "eval:doc.apply_on == 'Item Group'"
	);
	frm.set_df_property("item_groups", "hidden", is_gift_pool ? 1 : 0);
	frm.toggle_display("item_groups", !is_gift_pool);
	pn_unrequire_hidden_gift_pool_tables(frm);
	if (is_gift_pool) {
		pn_toggle_field_with_section(frm, "price_discount_slabs", false);
		pn_toggle_field_with_section(frm, "product_discount_slabs", false);
		frm.set_df_property(
			"gift_pool_items",
			"description",
			__(
				"Use <b>Select Multiple Items</b> to pick an item group and several free items at once. " +
					"<b>Free Qty</b> is the total free units (default 1), spread across those item codes in list order."
			)
		);
		frm.set_df_property("apply_on", "read_only", 1);
		frm.set_df_property("item_groups", "description", "");
	} else {
		frm.set_df_property("gift_pool_items", "description", "");
		frm.set_df_property("apply_on", "read_only", 0);
	}

	pn_setup_gift_pool_queries(frm);
	frm.refresh_field("item_groups");
}

function pn_unrequire_hidden_gift_pool_tables(frm) {
	if (frm.doc.promotion_type !== PROMOTION_TYPE_GIFT_POOL) {
		return;
	}
	frm.toggle_reqd("items", 0);
	frm.toggle_reqd("item_groups", 0);
	frm.toggle_reqd("brands", 0);
}

function pn_gift_pool_group_free_qty(frm, item_group) {
	const sibling = (frm.doc.gift_pool_items || []).find(
		(row) => row.item_group === item_group && cint(row.free_qty) > 0
	);
	return sibling ? cint(sibling.free_qty) : 1;
}

function pn_default_gift_pool_free_qty(frm, cdt, cdn) {
	const row = locals[cdt]?.[cdn];
	if (!row || cint(row.free_qty) > 0) {
		return;
	}
	frappe.model.set_value(cdt, cdn, "free_qty", pn_gift_pool_group_free_qty(frm, row.item_group));
}

function pn_sync_gift_pool_free_qty(frm, cdt, cdn) {
	const row = locals[cdt]?.[cdn];
	if (!row?.item_group || frm._pn_setting_gift_pool_rows) {
		return;
	}
	const qty = cint(row.free_qty) || 1;
	frm._pn_setting_gift_pool_rows = true;
	(frm.doc.gift_pool_items || []).forEach((other) => {
		if (other.item_group === row.item_group && other.name !== row.name && cint(other.free_qty) !== qty) {
			frappe.model.set_value(other.doctype, other.name, "free_qty", qty);
		}
	});
	frm._pn_setting_gift_pool_rows = false;
}

function pn_setup_gift_pool_queries(frm) {
	if (!frm.fields_dict.gift_pool_items) {
		return;
	}

	frm.set_query("item_group", "gift_pool_items", () => {
		// Do not restrict to the hidden Item Groups table. That used to
		// become {name: ["in", [""]]} when the table was empty, so the
		// link showed no groups at all.
		return {};
	});

	frm.set_query("item_code", "gift_pool_items", (_doc, cdt, cdn) => {
		const row = locals[cdt]?.[cdn] || {};
		return {
			query: "pos_next.api.gift_pool.gift_pool_item_query",
			filters: {
				item_group: row.item_group,
			},
		};
	});

	const grid = frm.fields_dict.gift_pool_items.grid;
	if (grid && !grid._pn_gift_pool_multi_btn) {
		grid.add_custom_button(__("Select Multiple Items"), () => {
			pn_open_gift_pool_item_picker(frm);
		});
		grid._pn_gift_pool_multi_btn = true;
	}
}

function pn_open_gift_pool_item_picker(frm) {
	const rows = frm.doc.gift_pool_items || [];
	const prefill_group = rows.find((row) => row.item_group)?.item_group || "";

	let picker;
	picker = new frappe.ui.form.MultiSelectDialog({
		doctype: "Item",
		target: frm,
		add_filters_group: 0,
		setters: {
			item_group: prefill_group || null,
		},
		primary_action_label: __("Add"),
		get_query() {
			const item_group =
				picker?.dialog?.fields_dict?.item_group?.get_value?.() || prefill_group;
			const filters = {
				disabled: 0,
				has_variants: 0,
				is_sales_item: 1,
			};
			if (item_group) {
				filters.item_group = item_group;
			}
			return {
				query: "erpnext.controllers.queries.item_query",
				filters,
			};
		},
		action(selections) {
			const item_group =
				picker.dialog.fields_dict.item_group.get_value() || prefill_group;
			if (!item_group) {
				frappe.msgprint(__("Please select an Item Group"));
				return;
			}
			if (!selections?.length) {
				frappe.msgprint(__("Please select at least one item"));
				return;
			}
			pn_add_gift_pool_selections(frm, item_group, selections);
			picker.dialog.hide();
		},
	});
}

function pn_add_gift_pool_selections(frm, item_group, item_codes) {
	const existing = new Set(
		(frm.doc.gift_pool_items || [])
			.filter((row) => row.item_group === item_group && row.item_code)
			.map((row) => row.item_code)
	);

	frappe.db
		.get_list("Item", {
			filters: { name: ["in", item_codes] },
			fields: ["name", "item_name"],
			limit: item_codes.length,
		})
		.then((items) => {
			frm._pn_setting_gift_pool_rows = true;
			const by_name = Object.fromEntries((items || []).map((item) => [item.name, item]));
			for (const item_code of item_codes) {
				if (existing.has(item_code)) {
					continue;
				}
				const empty = (frm.doc.gift_pool_items || []).find(
					(row) => row.item_group === item_group && !row.item_code
				);
				const values = {
					item_group,
					item_code,
					item_name: by_name[item_code]?.item_name || item_code,
					free_qty: pn_gift_pool_group_free_qty(frm, item_group),
				};
				if (empty) {
					frappe.model.set_value(empty.doctype, empty.name, values);
				} else {
					frm.add_child("gift_pool_items", values);
				}
				existing.add(item_code);
			}
			frm.refresh_field("gift_pool_items");
			frm._pn_setting_gift_pool_rows = false;
		});
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
 * Presentation only — the server owns the data.
 *
 * `pos_is_accumulative` is an authoring control. `normalize_accumulative_scheme`
 * projects it onto the canonical slab on every validate, so this function sets no
 * value the server does not also set; it just gets the irrelevant controls out of
 * the way. Anything enforced here is enforced there too, which is what keeps a
 * scheme built via the API as correct as one built in this form.
 *
 * The price discount slab is hidden rather than removed: ERPNext generates no
 * Pricing Rule from an empty child table, so the server keeps exactly one row
 * alive behind the scenes.
 */
function pn_sync_accumulative(frm) {
	const is_accumulative = !!frm.doc.pos_is_accumulative;
	const is_gift_pool = frm.doc.promotion_type === PROMOTION_TYPE_GIFT_POOL;


	pn_toggle_field_with_section(frm, "price_discount_slabs", !is_accumulative && !is_gift_pool);
	// Free items and Accumulative are mutually exclusive.
	pn_toggle_field_with_section(frm, "product_discount_slabs", !is_accumulative && !is_gift_pool);

	if (is_accumulative) {
		if (!frm.doc.mixed_conditions) {
			frm.set_value("mixed_conditions", 1);
		}
		if (!frm.doc.min_scopes_required) {
			frm.set_value("min_scopes_required", 1);
		}
	}

	// Mirrors the server, which pins these on the slab it maintains.
	const slab_grid = frm.fields_dict.price_discount_slabs?.grid;
	if (slab_grid) {
		for (const fieldname of PN_SLAB_DISCOUNT_FIELDS) {
			slab_grid.update_docfield_property(fieldname, "hidden", is_accumulative ? 1 : 0);
			slab_grid.update_docfield_property(fieldname, "in_list_view", is_accumulative ? 0 : 1);
		}
	}

	pn_toggle_scope_percentage(frm, is_accumulative);
}

/**
 * The Section Break a field sits under, resolved from the meta.
 *
 * Looked up rather than hardcoded — ERPNext's section names here are generated
 * (`section_break_14`) and would silently stop matching if they were renumbered.
 */
function pn_section_of(frm, fieldname) {
	let section = null;
	for (const df of frm.meta?.fields || []) {
		if (df.fieldtype === "Section Break") {
			section = df.fieldname;
		}
		if (df.fieldname === fieldname) {
			return section;
		}
	}
	return null;
}

/** Toggle a field together with the section that holds its heading. */
function pn_toggle_field_with_section(frm, fieldname, show) {
	frm.toggle_display(fieldname, show);

	const section = pn_section_of(frm, fieldname);
	if (section) {
		frm.toggle_display(section, show);
	}
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
	if (frm.doc.promotion_type === PROMOTION_TYPE_GIFT_POOL) {
		frm.set_df_property("item_groups", "description", "");
		return;
	}

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
