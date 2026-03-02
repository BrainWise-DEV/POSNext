frappe.ui.form.on("POS Profile", {
	setup(frm) {
		// Override the Customer field query to bypass the slow
		// get_filtered_dimensions query from Accounting Dimensions.
		// That query fetches ALL customers without pagination (~3s for 40K records).
		// This replaces it with a standard paginated search (~150ms).
		//
		// The dimensions code sets get_query asynchronously via
		// frappe.call → frappe.model.with_doctype callbacks, so a normal
		// set_query in setup/refresh would be overwritten.
		// We use Object.defineProperty to make our get_query immutable.
		const customerField = frm.fields_dict.customer;
		if (customerField) {
			const customerQuery = function () {
				return {
					filters: {
						disabled: 0,
					},
				};
			};
			customerField.get_query = customerQuery;
			Object.defineProperty(customerField, "get_query", {
				get() {
					return customerQuery;
				},
				set() {
					// Silently ignore overwrites from accounting dimensions
				},
				configurable: true,
			});
		}
	},
});
