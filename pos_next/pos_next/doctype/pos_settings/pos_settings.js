// Copyright (c) 2024, BrainWise and contributors
// For license information, please see license.txt

frappe.ui.form.on("POS Settings", {
	refresh(frm) {
		// Filter allowed users in Item Name Customization Table MultiSelect field, showing only users added to the POS Profile
		update_item_name_customization_query(frm)

		// Set query for loyalty program filtered by POS Profile company
		frm.set_query("default_loyalty_program", function () {
			if (!frm.doc.__company) {
				return { filters: {} };
			}
			return {
				filters: {
					company: frm.doc.__company,
				},
			};
		});

		// Fetch company when form loads
		if (frm.doc.pos_profile) {
			fetch_pos_profile_company(frm);
		}
	},

	pos_profile(frm) {
		// Filter allowed users in Item Name Customization Table MultiSelect field, showing only users added to the POS Profile
		update_item_name_customization_query(frm)

		// Clear loyalty program when POS Profile changes
		frm.set_value("default_loyalty_program", "");
		frm.doc.__company = null;

		if (frm.doc.pos_profile) {
			fetch_pos_profile_company(frm);
		}
	},
});

function fetch_pos_profile_company(frm) {
	frappe.db.get_value("POS Profile", frm.doc.pos_profile, "company", (r) => {
		if (r && r.company) {
			frm.doc.__company = r.company;
		}
	});
}

function update_item_name_customization_query(frm) {
	get_eligible_item_name_customization_users(frm).then((users) =>
		frm.set_query("allow_custom_item_name_in_cart_allowed_users", () => ({
			filters: {
				name: ["in", users],
			},
		}))
	);
}

async function get_eligible_item_name_customization_users(frm) {
	const pos_profile = frm.doc.pos_profile;

	if (!pos_profile) {
		return [];
	}

	const users = (await frappe.db.get_doc("POS Profile", pos_profile)).applicable_for_users;
	return users.map((user) => user.user);
}