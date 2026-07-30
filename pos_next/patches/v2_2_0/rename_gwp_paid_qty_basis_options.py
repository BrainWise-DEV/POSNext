# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Rename GWP paid-qty basis options from Min/Max Qty to Min/Max Price."""

import frappe

_RENAMES = {
	"Min Qty": "Min Price",
	"Max Qty": "Max Price",
}


def execute():
	for doctype in ("Pricing Rule", "Promotional Scheme Product Discount"):
		if not frappe.db.has_column(doctype, "gwp_paid_qty_basis"):
			continue
		for old_value, new_value in _RENAMES.items():
			frappe.db.sql(
				f"""
				UPDATE `tab{doctype}`
				SET gwp_paid_qty_basis = %s
				WHERE gwp_paid_qty_basis = %s
				""",
				(new_value, old_value),
			)

	frappe.db.commit()
