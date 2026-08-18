// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

// Frappe concatenates every app's doctype_js into one Function. Yield to
// posnext_promotions when it owns the authorization APIs.
(function () {
	if (frappe.boot && (frappe.boot.posnext_promotions_auth || frappe.boot.posnext_promotions)) {
		return;
	}

frappe.ui.form.on("User", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		frappe
			.call("pos_next.api.authorization.has_authorization_pin", { user: frm.doc.name })
			.then((r) => {
				const has_pin = Boolean(r.message && r.message.has_pin);

				const pin_length = (r.message && r.message.pin_length) || 4;
				const strict_pin_enforced = Boolean(r.message && r.message.strict_pin_enforced);
				const is_self = frm.doc.name === frappe.session.user;

				frm.add_custom_button(
					has_pin ? __("Change POS Authorization PIN") : __("Set POS Authorization PIN"),
					() => show_pin_dialog(frm, has_pin, is_self, pin_length, strict_pin_enforced),
					__("POS")
				);

				if (has_pin && frappe.user.has_role("System Manager")) {
					frm.add_custom_button(
						__("Remove POS Authorization PIN"),
						() => remove_pin(frm),
						__("POS")
					);
				}
			});
	},
});

function show_pin_dialog(frm, has_pin, is_self, pin_length, strict_pin_enforced) {

	const needs_current = has_pin && is_self;
	const strictness_hint = strict_pin_enforced
		? __("Avoid repeated digits and simple sequences. ")
		: "";

	const dialog = new frappe.ui.Dialog({
		title: __("POS Authorization PIN"),
		fields: [
			{
				fieldname: "current_pin",
				fieldtype: "Password",
				label: __("Current PIN"),
				depends_on: `eval:${needs_current}`,
				hidden: !needs_current,
				reqd: needs_current,
				length: pin_length,
			},
			{
				fieldname: "new_pin",
				fieldtype: "Password",
				label: __("New PIN"),
				reqd: 1,
				length: pin_length,
				description: __("Exactly {0} digits", [pin_length]),
			},
			{ fieldname: "confirm_pin", fieldtype: "Password", label: __("Confirm PIN"), reqd: 1, length: pin_length },
			{
				fieldtype: "HTML",
				options: `<p class="text-muted small">${strictness_hint}${__(
					"This PIN authorizes POS actions only. it cannot be used to sign in."
				)}</p>`,
			},
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			if (values.new_pin !== values.confirm_pin) {
				frappe.msgprint(__("The two PINs do not match"));
				return;
			}

			frappe
				.call("pos_next.api.authorization.set_authorization_pin", {
					user: frm.doc.name,
					new_pin: values.new_pin,
					current_pin: values.current_pin,
				})
				.then((r) => {
					if (r.message && r.message.success) {
						dialog.hide();
						frappe.show_alert({ message: __("PIN updated"), indicator: "green" });
						frm.refresh();
					} else if (r.message) {
						frappe.msgprint(r.message.message || __("Could not update the PIN"));
					}
				});
		},
	});

	dialog.show();
}

function remove_pin(frm) {
	frappe.confirm(
		__(
			"Remove the POS authorization PIN for {0}? They will no longer be able to approve POS actions.",
			[frm.doc.name]
		),
		() => {
			frappe
				.call("pos_next.api.authorization.clear_authorization_pin", { user: frm.doc.name })
				.then(() => {
					frappe.show_alert({ message: __("PIN removed"), indicator: "orange" });
					frm.refresh();
				});
		}
	);
}
})();
