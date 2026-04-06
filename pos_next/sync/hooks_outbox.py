# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Outbox hooks — capture transaction doc_events into Sync Outbox."""

import json

import frappe

from pos_next.sync.payload import to_payload


_METHOD_MAP = {
	"on_submit": "submit",
	"on_cancel": "cancel",
	"on_update": "update",
	"on_update_after_submit": "update",
	"after_insert": "insert",
	"on_trash": "delete",
}


def _method_to_operation(method):
	"""Convert Frappe doc_event method name to outbox operation."""
	return _METHOD_MAP.get(method, "update")


def _is_branch_site():
	"""Check if this site has an enabled Branch Sync Site Config."""
	cache_key = "pos_next_is_branch"
	result = frappe.cache().get_value(cache_key)
	if result is None:
		result = bool(frappe.db.get_value(
			"Sync Site Config", {"site_role": "Branch", "enabled": 1}, "name"
		))
		frappe.cache().set_value(cache_key, result, expires_in_sec=300)
	return result


def _get_priority(doctype_name):
	"""Get sync priority for a DocType from cache or registry."""
	cache_key = f"pos_next_sync_priority_{doctype_name}"
	prio = frappe.cache().get_value(cache_key)
	if prio is None:
		prio = frappe.db.get_value(
			"Sync DocType Rule",
			{"doctype_name": doctype_name, "parenttype": "Sync Site Config"},
			"priority",
		) or 100
		frappe.cache().set_value(cache_key, int(prio), expires_in_sec=300)
	return int(prio)


def enqueue_to_outbox(doc, method=None):
	"""
	Generic doc_event hook: capture document change into Sync Outbox.
	Only fires on Branch sites with sync enabled.
	"""
	if not _is_branch_site():
		return

	from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox

	operation = _method_to_operation(method)
	payload = json.dumps(to_payload(doc), default=str)
	priority = _get_priority(doc.doctype)

	SyncOutbox.enqueue(
		reference_doctype=doc.doctype,
		reference_name=doc.name,
		operation=operation,
		payload=payload,
		priority=priority,
	)
