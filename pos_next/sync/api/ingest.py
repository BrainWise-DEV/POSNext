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
			adapter.apply_incoming(payload, operation)

			payload_hash = compute_hash(payload)
			SyncRecordState.upsert(doctype, name, payload_hash, branch_code)

			results.append({"name": name, "sync_uuid": sync_uuid, "status": "ok"})
		except Exception as e:
			frappe.log_error(f"Ingest {doctype}/{name}: {e}", "Sync Ingest")
			results.append({"name": name, "sync_uuid": sync_uuid, "status": "error", "error": str(e)[:500]})

	frappe.db.commit()
	return {"results": results}
