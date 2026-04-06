# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Health endpoint for sync connectivity checks."""

import frappe
from frappe.utils import now_datetime


@frappe.whitelist(allow_guest=True)
def health():
	"""
	Return server time, version info, and site role.
	Public — no auth required. Used by branch to check connectivity.
	"""
	frappe_version = frappe.__version__
	pos_next_version = "unknown"
	try:
		import pos_next
		pos_next_version = getattr(pos_next, "__version__", "unknown")
	except Exception:
		pass

	site_role = frappe.db.get_value(
		"Sync Site Config", {"enabled": 1}, "site_role"
	) or "unconfigured"

	return {
		"server_time": str(now_datetime()),
		"frappe_version": frappe_version,
		"pos_next_version": pos_next_version,
		"site_role": site_role,
	}
