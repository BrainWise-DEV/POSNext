frappe.ui.form.on("POS Profile", {
	setup(frm) {
		// Override the Customer field query to bypass the slow
		// get_filtered_dimensions query from Accounting Dimensions.
		// That query fetches ALL customers without pagination (~3s for 40K records).
		// This replaces it with a standard paginated search (~150ms).
		frm.set_query("customer", function () {
			return {
				filters: {
					disabled: 0,
				},
			};
		});
	},
});
