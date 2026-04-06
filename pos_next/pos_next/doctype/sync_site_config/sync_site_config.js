// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sync Site Config", {
	refresh(frm) {
		if (frm.doc.site_role === "Branch" && !frm.is_new()) {
			frm.add_custom_button(__("Test Sync Connection"), () => {
				frappe.call({
					doc: frm.doc,
					method: "test_connection",
					freeze: true,
					freeze_message: __("Testing connection..."),
					callback(r) {
						if (!r.message) return;
						const msg = r.message.message;
						const ok = r.message.ok;
						frappe.msgprint({
							title: ok ? __("Connection OK") : __("Connection Failed"),
							message: msg,
							indicator: ok ? "green" : "red",
						});
					},
				});
			});
		}
	},
});
