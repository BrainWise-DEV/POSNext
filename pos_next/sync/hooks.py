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
		frappe.log_error("Sync Hooks", f"Tombstone write failed for {doc.doctype}/{doc.name}",)


def notify_branches_of_master_change(doc, method=None):
	"""
	on_update/on_trash hook for master DocTypes on Central.
	Signals all registered branches that they should pull updates.
	"""
	if not frappe.db.get_value("Sync Site Config", {"site_role": "Central", "enabled": 1}, "name"):
		return

	if method == "on_trash":
		write_tombstone_on_trash(doc, method)

	# Signal branches in the background to avoid blocking the main transaction
	frappe.enqueue(
		"pos_next.sync.hooks._enqueue_notify_branches",
		doctype=doc.doctype,
		name=doc.name,
		queue="short",
		enqueue_after_commit=True,
	)


def _enqueue_notify_branches(doctype, name):
	"""Worker job: Find all branches and call their pull_trigger API."""
	import requests
	from pos_next.sync.exceptions import SyncAuthError

	branches = frappe.get_all(
		"Sync Site Config",
		filters={"site_role": "Central", "enabled": 1},
		fields=["name", "registered_branch_url", "sync_api_key", "sync_api_secret"]
	)

	for branch in branches:
		if not branch.registered_branch_url:
			continue

		try:
			api_secret = frappe.get_doc("Sync Site Config", branch.name).get_password("sync_api_secret")
			headers = {"Authorization": f"token {branch.sync_api_key}:{api_secret}"}
			
			requests.post(
				f"{branch.registered_branch_url.rstrip('/')}/api/method/pos_next.sync.api.pull_trigger.trigger_pull",
				headers=headers,
				timeout=5,
			)
		except Exception:
			# Ignore branch-offline errors; they catch up via boot_session or next push round-trip
			pass
