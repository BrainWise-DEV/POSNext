# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Diagnostics for database deadlocks in the POS checkout path.

Two pieces, both cheap and both free of customer or payment data:

* ``log_lock_failure``: called from the ``except`` blocks of ``update_invoice`` and
  ``submit_invoice`` ONLY when a database lock error was raised (1213 deadlock / 1020 snapshot
  conflict as QueryDeadlockError, 1205 lock wait timeout as QueryTimeoutError). It writes one JSON
  line to ``logs/pos_next_deadlock.log`` saying where in the document save the
  deadlock hit (which child table, which statement shape, which checkout phase) and
  which isolation level the connection really had. It runs no extra query on the
  normal path and logs no SQL values, amounts, customer names or payment details.
  Customers appear only as a short hash, so two log lines can be matched to the same
  customer without exposing who it is.

* ``db_report``: a read-only report of the database settings that decide how a
  deadlock behaves, as seen by the application's own connection::

	bench --site <site> execute pos_next.diagnostics.db_report

The full deadlock report (both transactions, their statements and locks) can only be
produced by the database server: see docs/DEADLOCK_DIAGNOSTICS.md.
"""

import hashlib
import json
import logging
import re

import frappe

from pos_next.db_errors import classify

LOGGER_NAME = "pos_next_deadlock"  # also receives 1205 lock wait timeouts (see "kind")

_STATEMENT_RE = re.compile(
	r"^\s*(?P<verb>insert\s+into|insert\s+ignore\s+into|update|delete\s+from|select)\b"
	r".*?`(?P<table>tab[^`]+)`",
	re.IGNORECASE | re.DOTALL,
)
_LOCK_RE = re.compile(r"(for\s+update|lock\s+in\s+share\s+mode|for\s+share)\s*;?\s*$", re.IGNORECASE)


def statement_shape(query: str | None) -> str | None:
	"""``INSERT INTO `tabSales Invoice Item` `` or ``SELECT `tabSeries` FOR UPDATE``; never values."""
	if not query:
		return None
	text = str(query)
	match = _STATEMENT_RE.match(text)
	if not match:
		return None
	shape = f"{' '.join(match.group('verb').upper().split())} `{match.group('table')}`"
	lock = _LOCK_RE.search(text)
	return f"{shape} {' '.join(lock.group(1).upper().split())}" if lock else shape


def _failing_document(exc: BaseException) -> dict:
	"""The document being written when the error was raised, read from the traceback frames."""
	found = {}
	tb = exc.__traceback__
	while tb:
		frame = tb.tb_frame
		if frame.f_code.co_name in ("db_insert", "db_update", "delete_children", "update_children"):
			target = frame.f_locals.get("self")
			if target is not None and getattr(target, "doctype", None):
				found = {
					"db_call": frame.f_code.co_name,
					"doctype": target.doctype,
					"parent_doctype": getattr(target, "parenttype", None),
					"parentfield": getattr(target, "parentfield", None),
					"row_idx": getattr(target, "idx", None),
				}
		tb = tb.tb_next
	return found


def _failing_statement(exc: BaseException) -> str | None:
	"""Shape of the SQL statement that raised, read from Frappe's ``Database.sql`` frame.

	``frappe.db.last_query`` is not reliable after an error; the ``query`` local of the innermost
	``sql`` frame is the statement that failed. Only its shape is returned (verb, table, lock
	clause), never the text or its values.
	"""
	query = None
	tb = exc.__traceback__
	while tb:
		code = tb.tb_frame.f_code
		if code.co_name == "sql" and code.co_filename.endswith("frappe/database/database.py"):
			query = tb.tb_frame.f_locals.get("query") or query
		tb = tb.tb_next
	return statement_shape(query)


def _hash(value) -> str | None:
	return hashlib.sha1(str(value).encode()).hexdigest()[:8] if value else None


def _connection_settings() -> dict:
	"""Settings of THIS connection (the application's own, not an administrator's)."""
	try:
		row = frappe.db.sql(
			"""select @@session.tx_isolation, @@global.tx_isolation,
			@@session.innodb_lock_wait_timeout, @@global.innodb_lock_wait_timeout,
			@@global.innodb_rollback_on_timeout,
			@@session.lock_wait_timeout, @@global.lock_wait_timeout"""
		)[0]
	except Exception:
		return {}
	keys = (
		"tx_isolation_session",
		"tx_isolation_global",
		"innodb_lock_wait_timeout_session",
		"innodb_lock_wait_timeout_global",
		"innodb_rollback_on_timeout",
		"metadata_lock_wait_timeout_session",
		"metadata_lock_wait_timeout_global",
	)
	return dict(zip(keys, row, strict=True))


def describe_lock_failure(exc: BaseException, operation: str, doc=None, timer=None) -> dict:
	"""Build the context dict (no SQL values, no customer or payment data)."""
	info = {
		"operation": operation,
		**classify(exc),  # kind + the real MariaDB error number (1213, 1020, 1205, ...)
		"trace_id": None,
		"connection": _connection_settings(),
		# how long the request ran before failing: a 1205 sits close to innodb_lock_wait_timeout,
		# a deadlock (1213) fails fast
		"elapsed_ms": timer.elapsed_ms() if timer is not None else None,
		"failing": _failing_document(exc),
		"statement": _failing_statement(exc) or statement_shape(getattr(frappe.db, "last_query", None)),
		"completed_steps": list(getattr(timer, "steps", {}) or {}),
	}
	try:
		from frappe.monitor import get_trace_id

		info["trace_id"] = get_trace_id()
	except Exception:
		info["trace_id"] = None

	if doc is not None:
		get = doc.get if hasattr(doc, "get") else (lambda k, d=None: getattr(doc, k, d))
		wallet_modes = set(
			frappe.get_all("Mode of Payment", filters={"is_wallet_payment": 1}, pluck="name") or []
		)
		payments = get("payments") or []
		info["document"] = {
			"doctype": get("doctype"),
			"name": get("name") if not str(get("name") or "").startswith("new-") else None,
			"is_return": bool(get("is_return")),
			"rows": {
				"items": len(get("items") or []),
				"payments": len(payments),
				"taxes": len(get("taxes") or []),
				"sales_team": len(get("sales_team") or []),
			},
			"payment_modes": sorted({p.get("mode_of_payment") for p in payments if p.get("mode_of_payment")}),
			"has_wallet_payment": any(p.get("mode_of_payment") in wallet_modes for p in payments),
			"pos_profile": get("pos_profile"),
			"customer_hash": _hash(get("customer")),
		}
	return info


def log_lock_failure(exc: BaseException, operation: str, doc=None, timer=None) -> None:
	"""Write one JSON line about a database lock failure (1213 deadlock, 1205 lock wait timeout). Never raises: diagnostics must not break checkout."""
	try:
		info = describe_lock_failure(exc, operation, doc=doc, timer=timer)
		logger = frappe.logger(LOGGER_NAME, allow_site=True, file_count=5, max_size=1_000_000)
		# frappe.logger() defaults to ERROR, which would silently drop this warning.
		logger.setLevel(logging.WARNING)
		logger.warning(json.dumps(info, default=str))
	except Exception:
		logging.getLogger(LOGGER_NAME).exception("could not log deadlock context")


def db_report() -> None:
	"""Read-only: database settings that decide how deadlocks behave, as the app sees them."""
	frappe.set_user("Administrator")
	rows = frappe.db.sql(
		"""select @@global.tx_isolation, @@session.tx_isolation, @@global.binlog_format,
		@@innodb_print_all_deadlocks, @@innodb_deadlock_detect, @@innodb_lock_wait_timeout,
		@@innodb_autoinc_lock_mode, version()""",
	)[0]
	names = (
		"global_tx_isolation",
		"session_tx_isolation_of_this_connection",
		"binlog_format",
		"innodb_print_all_deadlocks",
		"innodb_deadlock_detect",
		"innodb_lock_wait_timeout_s",
		"innodb_autoinc_lock_mode",
		"server_version",
	)
	report = dict(zip(names, rows, strict=True))
	try:
		frappe.db.sql("show engine innodb status")
		report["app_user_can_read_innodb_status"] = True
	except Exception:
		report["app_user_can_read_innodb_status"] = False

	# Counters since the server started (no special privilege needed): how often deadlocks and
	# row-lock waits really happen on this server.
	status = dict(
		frappe.db.sql(
			"show global status where Variable_name in "
			"('Uptime', 'Innodb_deadlocks', 'Innodb_row_lock_waits', 'Innodb_row_lock_time_avg')"
		)
	)
	report["since_server_start"] = {k: status.get(k) for k in sorted(status)}
	print(json.dumps(report, indent=1, default=str))
