# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Install sync_uuid, origin_branch, synced_from_failover custom fields."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


TARGET_DOCTYPES = [
	"Sales Invoice",
	"Payment Entry",
	"Stock Ledger Entry",
	"POS Opening Shift",
	"POS Closing Shift",
	"Customer",
]


def execute():
	fields_per_doctype = {}
	for dt in TARGET_DOCTYPES:
		fields_per_doctype[dt] = [
			{
				"fieldname": "sync_uuid",
				"label": "Sync UUID",
				"fieldtype": "Data",
				"unique": 1,
				"read_only": 1,
				"no_copy": 1,
				"description": "Cross-site dedup key; set at creation",
				"insert_after": "name" if dt == "Customer" else None,
			},
			{
				"fieldname": "origin_branch",
				"label": "Origin Branch",
				"fieldtype": "Data",
				"read_only": 1,
				"no_copy": 1,
				"description": "branch_code of the site that originated this record",
			},
			{
				"fieldname": "synced_from_failover",
				"label": "Synced From Failover",
				"fieldtype": "Check",
				"read_only": 1,
				"no_copy": 1,
				"default": "0",
				"description": "1 when central wrote this record as a failover proxy for a branch",
			},
		]
	create_custom_fields(fields_per_doctype, update=True)
	frappe.db.commit()
	print(f"Installed sync custom fields on {len(TARGET_DOCTYPES)} doctypes")
