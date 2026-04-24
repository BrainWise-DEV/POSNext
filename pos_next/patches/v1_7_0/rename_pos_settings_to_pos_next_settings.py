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

MariaDB 1412 handling
=====================
frappe.rename_doc does the parent-table DDL (RENAME TABLE) before
updating link fields that point at the old doctype name. MariaDB
invalidates the session's table-metadata cache after the DDL and the
next UPDATE raises error 1412 ("Table definition has changed, please
retry transaction"). The DDL itself succeeded — the parent table and
tabDocType row are already renamed. We swallow 1412, reconnect, and
manually finish the link-field / dynamic-link / user-settings fixups
with a fresh session.

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


def _is_table_def_changed_error(exc: Exception) -> bool:
	msg = str(exc)
	return "1412" in msg or "Table definition has changed" in msg


def _finish_rename_manually(old: str, new: str) -> None:
	"""Re-run the post-DDL portion of rename_doc with a fresh connection."""
	from frappe.model.rename_doc import (
		get_link_fields,
		rename_dynamic_links,
		update_attachments,
		update_link_field_values,
		update_user_settings,
	)

	# Reset the session so the cursor has fresh table metadata after the DDL.
	frappe.db.commit()
	frappe.db.close()
	frappe.db.connect()

	link_fields = get_link_fields(new)
	update_link_field_values(link_fields, old, new, new)
	rename_dynamic_links(new, old, new)
	update_user_settings(old, new, link_fields)
	update_attachments(new, old, new)
	frappe.db.commit()


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

	# Clean transaction state before the DDL-heavy rename.
	frappe.db.commit()

	try:
		frappe.rename_doc(
			"DocType",
			"POS Settings",
			"POS Next Settings",
			force=True,
			show_alert=False,
			rebuild_search=False,
		)
	except Exception as exc:
		if not _is_table_def_changed_error(exc):
			raise
		# The RENAME TABLE + tabDocType update already succeeded; only the
		# downstream link-field update tripped on stale session metadata.
		# Finish manually with a fresh connection.
		_finish_rename_manually("POS Settings", "POS Next Settings")

	frappe.db.commit()
