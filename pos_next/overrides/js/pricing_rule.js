frappe.ui.form.on("Pricing Rule", {
	setup(frm) {
		frm.set_query("custom_batch", "items", (doc, cdt, cdn) => ({
			query: "pos_next.utils.link_queries.get_batches_for_item",
			filters: { item: locals[cdt][cdn].item_code || "" },
		}));
	},
});
