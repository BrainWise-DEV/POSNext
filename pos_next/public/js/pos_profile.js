// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

frappe.ui.form.on("POS Profile", {
	setup(frm) {
		frm.set_query("account", "posa_allowed_expense_accounts", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
				disabled: 0,
				root_type: "Expense",
			},
		}));
	},
});
