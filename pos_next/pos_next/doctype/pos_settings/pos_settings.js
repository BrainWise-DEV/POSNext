// Copyright (c) 2024, BrainWise and contributors
// For license information, please see license.txt

frappe.ui.form.on("POS Settings", {
	refresh(frm) {
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

		load_verification_providers(frm);

		// Fetch company when form loads
		if (frm.doc.pos_profile) {
			fetch_pos_profile_company(frm);
		}
	},

	pos_profile(frm) {
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

function load_verification_providers(frm) {
	frappe.call({
		method: "pos_next.integrations.otp.get_provider_options",
		callback(r) {
			const providers = r.message || [];
			// Stored value is the provider name; blank means the built-in one.
			const options = [""].concat(providers.map((p) => p.name));
			frm.set_df_property("verification_provider", "options", options.join("\n"));
			const rows = providers
				.map((p) => {
					const h = p.health || {};
					const state = h.ok ? __("OK") : __("Needs attention");
					const msg = h.message ? ` - ${frappe.utils.escape_html(h.message)}` : "";
					return `<li><b>${frappe.utils.escape_html(p.label)}</b>: ${state}${msg}</li>`;
				})
				.join("");
			frm.set_intro("", "blue");
			if (rows) {
				frm.set_intro(`<b>${__("Verification providers")}</b><ul>${rows}</ul>`, "blue");
			}
		},
	});
}
