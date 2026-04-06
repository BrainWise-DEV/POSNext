# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Branch-side masters puller — pulls Central→Branch DocTypes via watermark."""

import frappe
from frappe.utils import now_datetime, time_diff_in_seconds

from pos_next.sync.defaults import DEFAULT_PULL_MASTERS_INTERVAL_SECONDS, DEFAULT_BATCH_SIZE
from pos_next.sync.payload import compute_hash


def _ensure_adapters_loaded():
	"""Import all adapter modules so they register with the registry."""
	import pos_next.sync.adapters.item
	import pos_next.sync.adapters.item_price
	import pos_next.sync.adapters.customer
	import pos_next.sync.adapters.generic_master


def pull_if_due():
	"""
	Scheduler entry point (called every minute).
	Checks if this site is a Branch and if enough time has passed since last pull.
	"""
	cfg_name = frappe.db.get_value("Sync Site Config", {"site_role": "Branch", "enabled": 1}, "name")
	if not cfg_name:
		return  # Not a branch or not enabled

	cfg = frappe.get_doc("Sync Site Config", cfg_name)
	interval = cfg.pull_masters_interval_seconds or DEFAULT_PULL_MASTERS_INTERVAL_SECONDS

	if cfg.last_pull_masters_at:
		elapsed = time_diff_in_seconds(now_datetime(), cfg.last_pull_masters_at)
		if elapsed < interval:
			return  # Not due yet

	_ensure_adapters_loaded()

	# Build session and run pull
	try:
		from pos_next.sync.transport import build_session_from_config
		session = build_session_from_config()
		puller = MastersPuller(session)
		puller.run(cfg)
	except Exception as e:
		frappe.db.set_value("Sync Site Config", cfg_name, "last_sync_error", str(e)[:500])
		frappe.db.commit()
		_log("pull_masters", "failure", error=str(e))


class MastersPuller:
	"""Pulls master data from central for all Central→Branch DocTypes."""

	def __init__(self, session):
		self.session = session

	def run(self, cfg):
		"""Execute a full pull cycle for all enabled Central→Branch rules."""
		import time
		start = time.time()

		rules = self._get_pull_rules(cfg)
		total_upserted = 0
		total_deleted = 0
		total_errors = 0

		for rule in rules:
			dt = rule.doctype_name
			batch_size = rule.batch_size or DEFAULT_BATCH_SIZE
			watermark = self._get_watermark(dt)

			upserted, deleted, errors = self._pull_one_doctype(dt, watermark, batch_size)
			total_upserted += upserted
			total_deleted += deleted
			total_errors += errors

		# Update last pull timestamp
		frappe.db.set_value("Sync Site Config", cfg.name, "last_pull_masters_at", now_datetime())
		frappe.db.commit()

		duration_ms = int((time.time() - start) * 1000)
		_log(
			"pull_masters", "success" if total_errors == 0 else "partial",
			duration_ms=duration_ms,
			records_touched=total_upserted + total_deleted,
			context={"upserted": total_upserted, "deleted": total_deleted, "errors": total_errors},
		)

	def _get_pull_rules(self, cfg):
		"""Get enabled Central→Branch rules sorted by priority."""
		rules = []
		for rule in (cfg.synced_doctypes or []):
			if not rule.enabled:
				continue
			if rule.direction in ("Central\u2192Branch", "Bidirectional"):
				rules.append(rule)
		rules.sort(key=lambda r: r.priority or 100)
		return rules

	def _get_watermark(self, doctype_name):
		"""Get last_modified watermark for a DocType, or epoch."""
		from pos_next.pos_next.doctype.sync_watermark.sync_watermark import SyncWatermark
		wm = SyncWatermark.get_for(doctype_name)
		if wm and wm.last_modified:
			return str(wm.last_modified)
		return "2000-01-01 00:00:00"

	def _pull_one_doctype(self, doctype_name, since, batch_size):
		"""
		Pull all pages for one DocType. Returns (upserted, deleted, errors).
		"""
		total_upserted = 0
		total_deleted = 0
		total_errors = 0
		current_since = since

		while True:
			try:
				resp = self.session.get(
					"/api/method/pos_next.sync.api.changes.changes_since",
					params={
						"doctype": doctype_name,
						"since": current_since,
						"limit": batch_size,
					},
				)
				if resp.status_code != 200:
					total_errors += 1
					break

				data = resp.json().get("message", {})
				if not data:
					break

			except Exception as e:
				total_errors += 1
				frappe.log_error(f"Pull {doctype_name}: {e}", "MastersPuller")
				break

			# Apply upserts
			for payload in data.get("upserts", []):
				try:
					self._apply_upsert(doctype_name, payload)
					total_upserted += 1
				except Exception as e:
					total_errors += 1
					frappe.log_error(
						f"Apply {doctype_name}/{payload.get('name')}: {e}",
						"MastersPuller",
					)

			# Apply tombstones
			for tomb in data.get("tombstones", []):
				try:
					self._apply_tombstone(doctype_name, tomb["reference_name"])
					total_deleted += 1
				except Exception as e:
					total_errors += 1

			# Advance watermark
			next_since = data.get("next_since")
			if next_since:
				from pos_next.pos_next.doctype.sync_watermark.sync_watermark import SyncWatermark
				SyncWatermark.upsert(
					doctype_name, next_since,
					records_pulled=total_upserted,
				)
				frappe.db.commit()
				current_since = next_since

			if not data.get("has_more"):
				break

		return total_upserted, total_deleted, total_errors

	def _apply_upsert(self, doctype_name, payload):
		"""Apply a single upsert via the adapter."""
		from pos_next.sync import registry
		from pos_next.pos_next.doctype.sync_record_state.sync_record_state import SyncRecordState

		adapter = registry.get_adapter(doctype_name)

		# Check hash — skip if unchanged
		payload_hash = compute_hash(payload)
		existing_hash = SyncRecordState.get_hash(doctype_name, payload.get("name", ""))
		if existing_hash == payload_hash:
			return  # No change

		if adapter:
			adapter.validate_incoming(payload)
			adapter.apply_incoming(payload, "update")
		else:
			# No adapter — use default BaseSyncAdapter behavior
			from pos_next.sync.adapters.base import BaseSyncAdapter
			default = BaseSyncAdapter()
			default.doctype = doctype_name
			default.apply_incoming(payload, "update")

		# Record state
		SyncRecordState.upsert(doctype_name, payload.get("name", ""), payload_hash, "central")
		frappe.db.commit()

	def _apply_tombstone(self, doctype_name, reference_name):
		"""Delete a local record that was deleted on central."""
		if frappe.db.exists(doctype_name, reference_name):
			frappe.delete_doc(doctype_name, reference_name, ignore_permissions=True, force=True)
			# Remove record state
			state_name = frappe.db.get_value(
				"Sync Record State",
				{"reference_doctype": doctype_name, "reference_name": reference_name},
				"name",
			)
			if state_name:
				frappe.delete_doc("Sync Record State", state_name, ignore_permissions=True, force=True)
			frappe.db.commit()


def _log(operation, status, duration_ms=0, records_touched=0, error=None, context=None):
	"""Write a Sync Log entry."""
	try:
		from pos_next.pos_next.doctype.sync_log.sync_log import SyncLog
		SyncLog.record(
			operation=operation,
			status=status,
			duration_ms=duration_ms,
			records_touched=records_touched,
			error=error,
			context=context,
		)
		frappe.db.commit()
	except Exception:
		pass  # Don't let logging failure crash the puller
