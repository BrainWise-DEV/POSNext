// -*- coding: utf-8 -*-
// Copyright (c) 2025, POS Next and contributors
// For license information, please see license.txt

/**
 * Coupon Code List customization for POS Next
 *
 * Adds a "Create Gift Card" button to quickly create gift cards
 * managed by POS Next directly from the Coupon Code list.
 */

frappe.listview_settings["Coupon Code"] = {
	onload: function (listview) {
		// Add "Create Gift Card" button
		listview.page.add_inner_button(__("Create Gift Card"), function () {
			_show_create_gift_card_dialog();
		});
	},

	// Color coding for gift cards
	get_indicator: function (doc) {
		if (doc.pos_next_gift_card && doc.gift_card_amount > 0) {
			return [__("Gift Card Active"), "green", "pos_next_gift_card,=,1"];
		} else if (doc.pos_next_gift_card && doc.gift_card_amount <= 0) {
			return [__("Gift Card Depleted"), "gray", "pos_next_gift_card,=,1"];
		}
	},
};

/**
 * Show dialog to create a new gift card
 */
function _show_create_gift_card_dialog() {
	let d = new frappe.ui.Dialog({
		title: __("Create Gift Card"),
		fields: [
			{
				fieldname: "amount",
				fieldtype: "Currency",
				label: __("Amount"),
				reqd: 1,
				description: __("Gift card value"),
			},
			{
				fieldname: "company",
				fieldtype: "Link",
				options: "Company",
				label: __("Company"),
				reqd: 1,
				default: frappe.defaults.get_user_default("Company"),
			},
			{
				fieldname: "customer",
				fieldtype: "Link",
				options: "Customer",
				label: __("Customer"),
				description: __("Optional - leave empty for anonymous gift card"),
			},
			{
				fieldname: "validity_months",
				fieldtype: "Int",
				label: __("Validity (Months)"),
				default: 12,
				description: __("How long the gift card is valid"),
			},
		],
		primary_action_label: __("Create"),
		primary_action: function (values) {
			frappe.call({
				method: "pos_next.api.gift_cards.create_gift_card_manual",
				args: {
					amount: values.amount,
					company: values.company,
					customer: values.customer || null,
					validity_months: values.validity_months || 12,
				},
				callback: function (r) {
					if (r.message && r.message.success) {
						d.hide();
						frappe.show_alert(
							{
								message: __(
									"Gift Card {0} created with balance {1}",
									[r.message.coupon_code, r.message.formatted_amount]
								),
								indicator: "green",
							},
							10
						);

						// Refresh list view
						cur_list.refresh();

						// Show the created coupon code prominently
						_show_gift_card_created_dialog(r.message);
					}
				},
			});
		},
	});
	d.show();
}

/**
 * Show dialog with created gift card details (for printing/sharing)
 */
function _show_gift_card_created_dialog(gift_card) {
	let d = new frappe.ui.Dialog({
		title: __("Gift Card Created"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "gift_card_info",
				options: `
					<div style="text-align: center; padding: 20px;">
						<h2 style="margin-bottom: 10px;">${__("Gift Card Code")}</h2>
						<div style="font-size: 24px; font-weight: bold; font-family: monospace;
							background: var(--gray-100); padding: 15px; border-radius: 8px;
							letter-spacing: 2px; margin-bottom: 15px;">
							${gift_card.coupon_code}
						</div>
						<div style="font-size: 18px; color: var(--text-muted);">
							${__("Value")}: <strong>${gift_card.formatted_amount}</strong>
						</div>
						<div style="font-size: 14px; color: var(--text-muted); margin-top: 10px;">
							${__("Valid until")}: ${frappe.datetime.str_to_user(gift_card.valid_upto)}
						</div>
					</div>
				`,
			},
		],
		primary_action_label: __("Copy Code"),
		primary_action: function () {
			frappe.utils.copy_to_clipboard(gift_card.coupon_code);
			frappe.show_alert({
				message: __("Code copied to clipboard"),
				indicator: "green",
			});
		},
		secondary_action_label: __("Close"),
		secondary_action: function () {
			d.hide();
		},
	});
	d.show();
}
