// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bank Deposits", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.posting_date) {
			frm.set_value("posting_date", frappe.datetime.get_today());
		}

		frm.set_query("pos_profile", () => ({
			filters: { disabled: 0 },
		}));

		frm.set_query("pos_closing_shift", (doc) => ({
			query: "pos_next.pos_next.doctype.bank_deposits.bank_deposits.get_pos_closing_shifts",
			filters: { pos_profile: doc.pos_profile },
		}));
	},

	pos_closing_shift(frm) {
		if (!frm.doc.pos_closing_shift) return;

		frappe.db.get_value(
			"POS Closing Shift",
			frm.doc.pos_closing_shift,
			["pos_profile"],
			(r) => {
				if (r && r.pos_profile && r.pos_profile !== frm.doc.pos_profile) {
					frm.set_value("pos_profile", r.pos_profile);
				}
			},
		);
	},
});
