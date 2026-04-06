# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Sync doc_event hooks — tombstone recording on master deletion."""

import frappe


def write_tombstone_on_trash(doc, method=None):
	"""
	on_trash hook for synced master DocTypes.
	Records a tombstone so branches can replay the delete.
	"""
	from pos_next.pos_next.doctype.sync_tombstone.sync_tombstone import SyncTombstone
	try:
		SyncTombstone.record(doc.doctype, doc.name)
		frappe.db.commit()
	except Exception:
		# Don't block the delete if tombstone creation fails
		frappe.log_error(f"Tombstone write failed for {doc.doctype}/{doc.name}", "Sync Hooks")
