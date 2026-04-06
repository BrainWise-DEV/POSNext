# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Create the POS Next Sync Agent role."""

import frappe


ROLE_NAME = "POS Next Sync Agent"


def execute():
	if not frappe.db.exists("Role", ROLE_NAME):
		role = frappe.get_doc({
			"doctype": "Role",
			"role_name": ROLE_NAME,
			"desk_access": 0,
			"is_custom": 1,
		})
		role.insert(ignore_permissions=True)
		print(f"Created role: {ROLE_NAME}")
	else:
		print(f"Role already exists: {ROLE_NAME}")
	frappe.db.commit()
