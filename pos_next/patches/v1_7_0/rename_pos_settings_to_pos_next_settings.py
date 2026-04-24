"""Rename pos_next's 'POS Settings' DocType to 'POS Next Settings'.

Background
==========
pos_next historically shipped a per-profile (non-single) DocType named
'POS Settings'. ERPNext v16 introduces its own single 'POS Settings' with
fields like invoice_type and post_change_gl_entries, which collides with
pos_next's doctype and breaks 'bench migrate' (v16 patches 1 + 22).

This patch runs in pre_model_sync so it executes BEFORE ERPNext v16's
DocType sync creates the new single 'POS Settings'. It renames the
pos_next row in tabDocType and the underlying 'tabPOS Settings' MySQL
table to 'tabPOS Next Settings', leaving the 'POS Settings' name free
for ERPNext v16 to install into.

Idempotency
===========
Safe to re-run and safe on every entry state:

1. v15 site with pos_next's 'POS Settings' installed — the rename runs.
2. Already renamed — 'POS Settings' is absent or already an ERPNext single;
   the rename is skipped.
3. Fresh v16 install where pos_next is being installed for the first time —
   'POS Settings' either does not exist yet or exists as ERPNext's single;
   the rename is skipped.
"""

import frappe


def execute():
	if not frappe.db.table_exists("DocType"):
		return

	if not frappe.db.exists("DocType", "POS Settings"):
		return

	doctype_row = frappe.db.get_value(
		"DocType",
		"POS Settings",
		["module", "issingle"],
		as_dict=True,
	)
	if not doctype_row:
		return

	if doctype_row.issingle:
		# ERPNext v16's single already owns the name — nothing to rename.
		return

	if doctype_row.module != "POS Next":
		# A non-single 'POS Settings' owned by something other than pos_next
		# is unexpected. Log and bail rather than mutate unknown state.
		frappe.log_error(
			title="pos_next rename_pos_settings patch skipped",
			message=(
				f"Expected 'POS Settings' to belong to module 'POS Next', "
				f"found '{doctype_row.module}'. Skipping rename."
			),
		)
		return

	if frappe.db.exists("DocType", "POS Next Settings"):
		# Previous partial run left both around — drop the stale source row
		# so model sync can re-create the canonical 'POS Settings' single.
		frappe.delete_doc("DocType", "POS Settings", force=True, ignore_permissions=True)
		frappe.db.commit()
		return

	frappe.rename_doc(
		"DocType",
		"POS Settings",
		"POS Next Settings",
		force=True,
		show_alert=False,
	)
	frappe.db.commit()
