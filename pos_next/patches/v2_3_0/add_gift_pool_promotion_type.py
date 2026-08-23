# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Add Gift Pool to Promotional Scheme / Pricing Rule promotion_type options."""

import frappe

_OPTIONS = "\nItem Level Discount\nAuto Discount\nGWP\nGift Pool"

_FIELDS = (
	"Promotional Scheme-custom_promotion_type",
	"Pricing Rule-custom_promotion_type",
)


def execute():
	for name in _FIELDS:
		if frappe.db.exists("Custom Field", name):
			frappe.db.set_value("Custom Field", name, "options", _OPTIONS)
	frappe.clear_cache(doctype="Promotional Scheme")
	frappe.clear_cache(doctype="Pricing Rule")
