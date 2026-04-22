# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Branch-side API: accept pull triggers from Central."""

import frappe


@frappe.whitelist()
def trigger_pull():
	"""
	Central-side trigger: notify the branch that master data has changed.
	"""
	cfg_name = frappe.db.get_value("Sync Site Config", {"site_role": "Branch", "enabled": 1}, "name")
	if not cfg_name:
		return {"ok": False, "message": "Not a Branch site"}

	# Enqueue immediate pull
	frappe.enqueue(
		"pos_next.sync.masters_puller.pull_now",
		queue="short",
		job_id="sync_pull_now",
		deduplicate=True,
		enqueue_after_commit=True,
	)

	return {"ok": True, "message": "Pull enqueued"}
