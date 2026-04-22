# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Reconnection catch-up: triggered on every Frappe desk boot (boot_session hook)."""

import frappe


def on_boot(bootinfo):
	"""On Branch sites, enqueue a drain + pull so any offline gap is closed when desk opens."""
	if not frappe.db.get_value("Sync Site Config", {"site_role": "Branch", "enabled": 1}, "name"):
		return

	frappe.enqueue(
		"pos_next.sync.masters_puller.pull_now",
		queue="short",
		job_id="sync_pull_now",
		deduplicate=True,
		enqueue_after_commit=True,
	)
	frappe.enqueue(
		"pos_next.sync.outbox_drainer.drain_outbox",
		queue="short",
		job_id="sync_drain_outbox",
		deduplicate=True,
		enqueue_after_commit=True,
	)
