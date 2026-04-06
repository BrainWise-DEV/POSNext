# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Branch-side masters puller — pulls Central→Branch DocTypes via watermark."""

import importlib
import pkgutil
import time

import frappe
from frappe.utils import now_datetime, time_diff_in_seconds

from pos_next.sync import registry
from pos_next.sync.defaults import (
	DEFAULT_BATCH_SIZE,
	DEFAULT_PULL_MASTERS_INTERVAL_SECONDS,
	DIRECTIONS_PULL,
)
from pos_next.sync.payload import compute_hash
from pos_next.pos_next.doctype.sync_log.sync_log import SyncLog
from pos_next.pos_next.doctype.sync_record_state.sync_record_state import SyncRecordState
from pos_next.pos_next.doctype.sync_watermark.sync_watermark import SyncWatermark


def _ensure_adapters_loaded():
	"""Auto-discover and import all adapter modules so they register with the registry."""
	import pos_next.sync.adapters as _pkg
	for info in pkgutil.iter_modules(_pkg.__path__, _pkg.__name__ + "."):
		if not info.name.endswith(".base"):
			importlib.import_module(info.name)


def pull_if_due():
	"""
	Scheduler entry point (called every minute by cron).
	Checks if this site is a Branch and if enough time has passed since last pull.
	"""
	cfg_name = frappe.db.get_value("Sync Site Config", {"site_role": "Branch", "enabled": 1}, "name")
	if not cfg_name:
		return

	cfg = frappe.get_doc("Sync Site Config", cfg_name)
	interval = cfg.pull_masters_interval_seconds or DEFAULT_PULL_MASTERS_INTERVAL_SECONDS

	if cfg.last_pull_masters_at:
		elapsed = time_diff_in_seconds(now_datetime(), cfg.last_pull_masters_at)
		if elapsed < interval:
			return

	_ensure_adapters_loaded()

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
		start = time.time()

		rules = self._get_pull_rules(cfg)
		total_upserted = 0
		total_deleted = 0
		total_errors = 0

		for rule in rules:
			dt = rule.doctype_name
			batch_size = rule.batch_size or DEFAULT_BATCH_SIZE
			watermark = self._get_watermark(dt)
			adapter = registry.get_adapter(dt)

			upserted, deleted, errors = self._pull_one_doctype(dt, watermark, batch_size, adapter)
			total_upserted += upserted
			total_deleted += deleted
			total_errors += errors

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
		rules = [
			rule for rule in (cfg.synced_doctypes or [])
			if rule.enabled and rule.direction in DIRECTIONS_PULL
		]
		rules.sort(key=lambda r: r.priority or 100)
		return rules

	def _get_watermark(self, doctype_name):
		"""Get last_modified watermark for a DocType, or epoch."""
		wm = SyncWatermark.get_for(doctype_name)
		if wm and wm.last_modified:
			return str(wm.last_modified)
		return "2000-01-01 00:00:00"

	def _pull_one_doctype(self, doctype_name, since, batch_size, adapter=None):
		"""Pull all pages for one DocType. Returns (upserted, deleted, errors)."""
		total_upserted = 0
		total_deleted = 0
		total_errors = 0
		current_since = since

		# Fall back to default adapter if none registered
		if not adapter:
			from pos_next.sync.adapters.base import BaseSyncAdapter
			adapter = BaseSyncAdapter()
			adapter.doctype = doctype_name

		while True:
			try:
				resp = self.session.get(
					"/api/method/pos_next.sync.api.changes.changes_since",
					params={"doctype": doctype_name, "since": current_since, "limit": batch_size},
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
					if self._apply_upsert(doctype_name, payload, adapter):
						total_upserted += 1
				except Exception as e:
					total_errors += 1
					frappe.log_error(f"Apply {doctype_name}/{payload.get('name')}: {e}", "MastersPuller")

			# Apply tombstones
			for tomb in data.get("tombstones", []):
				try:
					self._apply_tombstone(doctype_name, tomb["reference_name"])
					total_deleted += 1
				except Exception as e:
					total_errors += 1
					frappe.log_error(f"Tombstone {doctype_name}/{tomb.get('reference_name')}: {e}", "MastersPuller")

			# Advance watermark and commit the batch
			next_since = data.get("next_since")
			if next_since:
				SyncWatermark.upsert(doctype_name, next_since, records_pulled=total_upserted)
				current_since = next_since

			frappe.db.commit()

			if not data.get("has_more"):
				break

		return total_upserted, total_deleted, total_errors

	def _apply_upsert(self, doctype_name, payload, adapter):
		"""Apply a single upsert via the adapter. Returns True if applied, False if skipped."""
		payload_hash = compute_hash(payload)
		existing_hash = SyncRecordState.get_hash(doctype_name, payload.get("name", ""))
		if existing_hash == payload_hash:
			return False

		adapter.validate_incoming(payload)
		adapter.apply_incoming(payload, "update")
		SyncRecordState.upsert(doctype_name, payload.get("name", ""), payload_hash, "central")
		return True

	def _apply_tombstone(self, doctype_name, reference_name):
		"""Delete a local record that was deleted on central."""
		if frappe.db.exists(doctype_name, reference_name):
			frappe.delete_doc(doctype_name, reference_name, ignore_permissions=True, force=True)
		# Clean up record state
		frappe.db.delete("Sync Record State", {
			"reference_doctype": doctype_name,
			"reference_name": reference_name,
		})


def _log(operation, status, duration_ms=0, records_touched=0, error=None, context=None):
	"""Write a Sync Log entry."""
	try:
		SyncLog.record(
			operation=operation, status=status, duration_ms=duration_ms,
			records_touched=records_touched, error=error, context=context,
		)
		frappe.db.commit()
	except Exception:
		pass
