"""Reclaim the `POS Settings` DocType from ERPNext.

ERPNext ships a Single `POS Settings` (module Accounts) with only
`invoice_fields` and `pos_search_fields`. POS Next ships its own
non-Single `POS Settings` (module POS Next) with per-profile config and
the `barcode_rules` child table that `pos_next.services.barcode`
depends on.

Because both apps export a DocType with the same name, whichever app
migrates last wins on disk. ERPNext is in our `required_apps`, so it
runs after us and reinstates its Single version, which silently breaks
the barcode resolver (every weighted barcode falls back to "Item not
found"). This patch runs in `pre_model_sync` so it executes BEFORE
doctype sync — it removes the legacy meta + table, then sync re-imports
our JSON cleanly. Idempotent: if the live doctype is already ours, it
exits early.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "POS Settings"):
		return

	row = frappe.db.get_value(
		"DocType", "POS Settings", ["module", "issingle"], as_dict=True
	)
	if row and row.module == "POS Next" and not row.issingle:
		return

	frappe.db.sql("DROP TABLE IF EXISTS `tabPOS Settings`")
	frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = 'POS Settings'")
	frappe.db.sql("DELETE FROM `tabDocField` WHERE parent = 'POS Settings'")
	frappe.db.sql("DELETE FROM `tabDocPerm` WHERE parent = 'POS Settings'")
	frappe.db.sql("DELETE FROM `tabDocType` WHERE name = 'POS Settings'")
	frappe.db.commit()
