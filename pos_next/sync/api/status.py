# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Sync status API — returns dashboard data for the Sync Site Config form."""

import frappe


@frappe.whitelist()
def get_sync_status():
	"""
	Return sync status summary for the current site.
	Used by the Sync Site Config form to show a live dashboard.
	"""
	cfg = frappe.db.get_value(
		"Sync Site Config",
		{"enabled": 1},
		["name", "site_role", "branch_code", "last_pull_masters_at", "last_sync_error"],
		as_dict=True,
	)
	if not cfg:
		return {"configured": False}

	# Outbox stats
	outbox_pending = frappe.db.count("Sync Outbox", {"sync_status": "pending"})
	outbox_failed = frappe.db.count("Sync Outbox", {"sync_status": "failed"})
	outbox_dead = frappe.db.count("Sync Dead Letter")

	# Conflict queue
	conflicts_pending = frappe.db.count("Sync Conflict", {"status": "pending"})

	# Recent sync logs
	recent_logs = frappe.get_all(
		"Sync Log",
		fields=["operation", "status", "duration_ms", "records_touched", "error", "creation"],
		order_by="creation desc",
		limit_page_length=10,
	)

	# Watermarks
	watermarks = frappe.get_all(
		"Sync Watermark",
		fields=["doctype_name", "last_modified", "last_pulled_at", "records_pulled"],
		order_by="doctype_name asc",
	)

	return {
		"configured": True,
		"site_role": cfg.site_role,
		"branch_code": cfg.branch_code,
		"last_pull_masters_at": str(cfg.last_pull_masters_at) if cfg.last_pull_masters_at else None,
		"last_sync_error": cfg.last_sync_error,
		"outbox": {
			"pending": outbox_pending,
			"failed": outbox_failed,
			"dead": outbox_dead,
		},
		"conflicts_pending": conflicts_pending,
		"recent_logs": recent_logs,
		"watermarks": watermarks,
	}
