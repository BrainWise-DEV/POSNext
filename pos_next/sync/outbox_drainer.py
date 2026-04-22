# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Branch-side outbox drainer — pushes transactions to central."""

import json
from datetime import timedelta

import frappe
from frappe.utils import now_datetime, time_diff_in_seconds

from pos_next.sync.defaults import (
	DEFAULT_BATCH_SIZE,
	DEFAULT_PUSH_INTERVAL_SECONDS,
	MAX_ATTEMPTS_BEFORE_DEAD,
)
from pos_next.sync.exceptions import SyncUnauthorizedError
from pos_next.sync.masters_puller import _ensure_adapters_loaded
from pos_next.pos_next.doctype.sync_log.sync_log import SyncLog


def push_if_due():
	"""
	Scheduler entry point (called every minute by cron).
	Checks if this site is a Branch and if enough time has passed since last push.
	"""
	cfg_name = frappe.db.get_value("Sync Site Config", {"site_role": "Branch", "enabled": 1}, "name")
	if not cfg_name:
		return

	cfg = frappe.get_doc("Sync Site Config", cfg_name)
	interval = cfg.push_interval_seconds or DEFAULT_PUSH_INTERVAL_SECONDS

	if cfg.last_push_at:
		elapsed = time_diff_in_seconds(now_datetime(), cfg.last_push_at)
		if elapsed < interval:
			return

	_ensure_adapters_loaded()

	try:
		from pos_next.sync.transport import build_session_from_config
		session = build_session_from_config()
		drainer = OutboxDrainer(session, branch_code=cfg.branch_code)
		acked, failed, dead = drainer.drain()

		frappe.db.set_value("Sync Site Config", cfg_name, "last_push_at", now_datetime())
		frappe.db.commit()

		_log(
			"push_outbox", "success" if (failed + dead) == 0 else "partial",
			records_touched=acked + failed + dead,
			context={"acked": acked, "failed": failed, "dead": dead},
		)
	except Exception as e:
		frappe.db.set_value("Sync Site Config", cfg_name, "last_sync_error", str(e)[:500])
		frappe.db.commit()
		_log("push_outbox", "failure", error=str(e))


class OutboxDrainer:
	"""Drains pending Sync Outbox rows by POSTing to central's ingest API."""

	def __init__(self, session, branch_code):
		self.session = session
		self.branch_code = branch_code

	def drain(self):
		"""Process all drainable outbox rows. Returns (acked, failed, dead)."""
		total_acked = 0
		total_failed = 0
		total_dead = 0

		rows = self._get_drainable_rows()
		if not rows:
			return 0, 0, 0

		# Group by doctype
		by_doctype = {}
		for row in rows:
			by_doctype.setdefault(row.reference_doctype, []).append(row)

		for dt, dt_rows in by_doctype.items():
			acked, failed, dead = self._push_batch(dt, dt_rows)
			total_acked += acked
			total_failed += failed
			total_dead += dead

		frappe.db.commit()
		return total_acked, total_failed, total_dead

	def _get_drainable_rows(self):
		"""Get outbox rows ready for push (pending or failed with backoff expired)."""
		return frappe.db.sql("""
			SELECT name, reference_doctype, reference_name, operation, payload, attempts
			FROM `tabSync Outbox`
			WHERE sync_status IN ('pending', 'failed')
			AND (next_attempt_at IS NULL OR next_attempt_at <= %(now)s)
			ORDER BY priority ASC, creation ASC
			LIMIT %(limit)s
		""", {"now": now_datetime(), "limit": DEFAULT_BATCH_SIZE}, as_dict=True)

	def _push_batch(self, doctype, rows):
		"""Push a batch of rows for one DocType to central. Returns (acked, failed, dead)."""
		acked = 0
		failed = 0
		dead = 0

		records = []
		for row in rows:
			payload = row.payload
			if isinstance(payload, str):
				try:
					payload = json.loads(payload)
				except json.JSONDecodeError:
					payload = {}
			records.append({"operation": row.operation, "payload": payload})

		try:
			resp = self.session.post(
				"/api/method/pos_next.sync.api.ingest.ingest",
				json={"doctype": doctype, "branch_code": self.branch_code, "records": records},
			)
			if resp.status_code != 200:
				if resp.status_code == 401:
					raise SyncUnauthorizedError("Central rejected sync API credentials")
				for row in rows:
					self._mark_failed(row, f"HTTP {resp.status_code}")
					failed += 1
				return acked, failed, dead

			results = resp.json().get("message", {}).get("results", [])
			for i, row in enumerate(rows):
				if i < len(results):
					result = results[i]
					if result.get("status") in ("ok", "skipped"):
						self._mark_acked(row)
						acked += 1
					else:
						error = result.get("error", "Unknown error")
						if self._should_dead_letter(row):
							self._move_to_dead_letter(row, error)
							dead += 1
						else:
							self._mark_failed(row, error)
							failed += 1
				else:
					self._mark_failed(row, "No result from central")
					failed += 1

		except Exception as e:
			for row in rows:
				self._mark_failed(row, str(e))
				failed += 1

		return acked, failed, dead

	def _mark_acked(self, row):
		frappe.db.set_value("Sync Outbox", row.name, {
			"sync_status": "acked",
			"acked_at": now_datetime(),
		})

	def _mark_failed(self, row, error):
		attempts = (row.attempts or 0) + 1
		backoff_seconds = min(2 ** attempts, 3600)
		frappe.db.set_value("Sync Outbox", row.name, {
			"sync_status": "failed",
			"attempts": attempts,
			"last_error": str(error)[:500],
			"next_attempt_at": now_datetime() + timedelta(seconds=backoff_seconds),
		})

	def _should_dead_letter(self, row):
		return (row.attempts or 0) >= MAX_ATTEMPTS_BEFORE_DEAD

	def _move_to_dead_letter(self, row, error):
		frappe.get_doc({
			"doctype": "Sync Dead Letter",
			"reference_doctype": row.reference_doctype,
			"reference_name": row.reference_name,
			"operation": row.operation,
			"last_error": str(error)[:500],
			"attempts": (row.attempts or 0) + 1,
			"payload": row.payload,
			"moved_at": now_datetime(),
		}).insert(ignore_permissions=True)
		frappe.delete_doc("Sync Outbox", row.name, ignore_permissions=True, force=True)


def _log(operation, status, duration_ms=0, records_touched=0, error=None, context=None):
	try:
		SyncLog.record(
			operation=operation, status=status, duration_ms=duration_ms,
			records_touched=records_touched, error=error, context=context,
		)
		frappe.db.commit()
	except Exception:
		pass
