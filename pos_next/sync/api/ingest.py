# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Central-side API: receive and apply pushed transactions from branches."""

import json

import frappe

from pos_next.sync import registry
from pos_next.sync.adapters.base import BaseSyncAdapter
from pos_next.sync.payload import compute_hash
from pos_next.sync.masters_puller import _ensure_adapters_loaded
from pos_next.pos_next.doctype.sync_record_state.sync_record_state import SyncRecordState


@frappe.whitelist()
def ingest(doctype, branch_code, records):
	"""
	Receive a batch of records pushed from a branch.

	Returns: {"results": [{name, sync_uuid, status, error?}, ...]}
	"""
	_ensure_adapters_loaded()

	if isinstance(records, str):
		records = json.loads(records)

	adapter = registry.get_adapter(doctype)
	if not adapter:
		adapter = BaseSyncAdapter()
		adapter.doctype = doctype

	results = []
	for record in records:
		operation = record.get("operation", "update")
		payload = record.get("payload", {})
		name = payload.get("name", "")
		sync_uuid = payload.get("sync_uuid", "")

		try:
			# Idempotency: skip if sync_uuid already exists locally
			if sync_uuid and frappe.db.exists(doctype, {"sync_uuid": sync_uuid}):
				results.append({"name": name, "sync_uuid": sync_uuid, "status": "skipped"})
				continue

			adapter.validate_incoming(payload)
			local_name = adapter.apply_incoming(payload, operation) or name

			payload_hash = compute_hash(payload)
			SyncRecordState.upsert(doctype, name, payload_hash, branch_code)
			frappe.db.commit()

			# When a Bidirectional doctype (e.g. Item) is pushed by one branch,
			# our adapters use raw SQL, so the doc_event `on_update` hook that
			# normally fires `notify_branches_of_master_change` does NOT run.
			# Manually trigger fan-out so the other branches pick this change up.
			if _is_bidirectional(doctype) and operation != "delete":
				frappe.enqueue(
					"pos_next.sync.hooks._enqueue_notify_branches",
					doctype=doctype,
					name=local_name,
					queue="short",
					enqueue_after_commit=True,
				)

			results.append({"name": name, "sync_uuid": sync_uuid, "status": "ok"})
		except Exception as e:
			frappe.db.rollback()
			frappe.log_error("Sync Ingest", f"Ingest {doctype}/{name}: {e}")
			results.append({"name": name, "sync_uuid": sync_uuid, "status": "error", "error": str(e)[:500]})

	try:
		pull_hint = _check_for_master_updates(branch_code)
	except Exception:
		pull_hint = False

	return {
		"results": results,
		"pull_hint": pull_hint,
	}


def _is_bidirectional(doctype):
	"""True if any Sync Site Config rule classifies this doctype as Bidirectional."""
	return bool(frappe.db.exists("Sync DocType Rule", {
		"doctype_name": doctype,
		"direction": "Bidirectional",
		"enabled": 1,
	}))


def _check_for_master_updates(branch_code):
	"""
	Central-side: check if any master data changed since this branch last pulled.
	Returns True if a pull is recommended.
	"""
	from pos_next.sync.defaults import DIRECTIONS_PULL
	
	cfg_name = frappe.db.get_value("Sync Site Config", {"branch_code": branch_code, "site_role": "Central"}, "name")
	if not cfg_name:
		return False
	
	cfg = frappe.get_doc("Sync Site Config", cfg_name)
	last_pull = cfg.last_pull_masters_at
	if not last_pull:
		return True

	for rule in (cfg.synced_doctypes or []):
		if not rule.enabled or rule.direction not in DIRECTIONS_PULL:
			continue
		
		if frappe.db.exists(rule.doctype_name, {"modified": (">", last_pull)}):
			return True
	
	if frappe.db.exists("Sync Tombstone", {"deleted_at": (">", last_pull)}):
		for rule in (cfg.synced_doctypes or []):
			if rule.enabled and rule.direction in DIRECTIONS_PULL:
				if frappe.db.exists("Sync Tombstone", {"reference_doctype": rule.doctype_name, "deleted_at": (">", last_pull)}):
					return True

	return False
