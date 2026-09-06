// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

function set_pos_closing_shift_query(frm) {
	frm.set_query("pos_closing_shift", () => ({
		query: "pos_next.pos_next.doctype.bank_deposits.bank_deposits.get_pos_closing_shifts",
		filters: {
			pos_profile: frm.doc.pos_profile,
		},
	}));
}

frappe.ui.form.on("Bank Deposits", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.posting_date) {
			frm.set_value("posting_date", frappe.datetime.get_today());
		}

		frm.set_query("pos_profile", () => ({
			filters: { disabled: 0 },
		}));

		set_pos_closing_shift_query(frm);
	},

	refresh(frm) {
		set_pos_closing_shift_query(frm);
	},

	pos_profile(frm) {
		if (frm.doc.pos_closing_shift) {
			frm.set_value("pos_closing_shift", "");
		}
	},

	pos_closing_shift(frm) {
		if (!frm.doc.pos_closing_shift) return;

		frappe.db.get_value(
			"POS Closing Shift",
			frm.doc.pos_closing_shift,
			["pos_profile", "docstatus"],
			(r) => {
				if (!r) return;

				if (r.docstatus !== 1) {
					frappe.msgprint({
						title: __("Invalid Shift"),
						message: __("Only submitted POS Closing Shifts can be selected."),
						indicator: "red",
					});
					frm.set_value("pos_closing_shift", "");
					return;
				}

				if (r.pos_profile && r.pos_profile !== frm.doc.pos_profile) {
					frm.set_value("pos_profile", r.pos_profile);
				}
			}
		);
	},
});
