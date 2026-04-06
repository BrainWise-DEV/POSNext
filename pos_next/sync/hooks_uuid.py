# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Auto-fill sync_uuid on creation of sync-tracked documents."""

import uuid

import frappe


def set_sync_uuid_if_missing(doc, method=None):
	"""Before-insert hook: set sync_uuid to a fresh UUID4 if not already set."""
	if getattr(doc, "sync_uuid", None):
		return
	doc.sync_uuid = str(uuid.uuid4())


def set_origin_branch_if_missing(doc, method=None):
	"""Before-insert hook: set origin_branch to this site's branch_code if empty."""
	if getattr(doc, "origin_branch", None):
		return
	branch_code = _get_branch_code()
	if branch_code:
		doc.origin_branch = branch_code


def _get_branch_code():
	"""Get this site's branch_code, cached for the process lifetime."""
	cache_key = "pos_next_branch_code"
	code = frappe.cache().get_value(cache_key)
	if code is None:
		code = frappe.db.get_value("Sync Site Config", {"site_role": "Branch"}, "branch_code") or ""
		frappe.cache().set_value(cache_key, code, expires_in_sec=300)
	return code or None
