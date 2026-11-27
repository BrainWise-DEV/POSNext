# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Lightweight step timing for the invoice submit path.

Usage::

        timer = StepTimer("submit_invoice", pos_profile=profile)
        ...
        timer.mark("validate_stock")  # records time since the previous mark
        ...
        timer.finish(invoice=name, items=len(doc.items))

Calls slower than ``pos_next_slow_submit_ms`` (site config, default 5000) are
written as one JSON line at WARNING to ``sites/<site>/logs/pos_next_perf.log``.
Set ``pos_next_perf_log_all`` in site config to also log every call (INFO).
For tooling, set ``frappe.flags.pos_next_collect_perf = True`` and read the
records from ``frappe.flags.pos_next_perf_records``.
The timer never raises and never touches the database.
"""

import json
import logging
import time

import frappe

DEFAULT_SLOW_MS = 5000
LOGGER_NAME = "pos_next_perf"


def _ms(seconds: float) -> int:
	return int(round(seconds * 1000))


class StepTimer:
	def __init__(self, operation: str, **context):
		self.operation = operation
		self.context = context
		self._start = self._last = time.perf_counter()
		self.steps: dict[str, int] = {}

	def mark(self, step: str) -> None:
		"""Record the time since the previous mark (or start) under ``step``."""
		now = time.perf_counter()
		self.steps[step] = self.steps.get(step, 0) + _ms(now - self._last)
		self._last = now

	def elapsed_ms(self) -> int:
		"""Milliseconds since this timer started (includes the step still running)."""
		return _ms(time.perf_counter() - self._start)

	def finish(self, status: str = "ok", **context) -> int:
		"""Emit the log line and return the total duration in ms."""
		total_ms = _ms(time.perf_counter() - self._start)
		try:
			configured = frappe.conf.get("pos_next_slow_submit_ms")
			slow_ms = DEFAULT_SLOW_MS if configured is None else int(configured)
			payload = {
				"op": self.operation,
				"status": status,
				"total_ms": total_ms,
				"steps_ms": self.steps,
				**self.context,
				**context,
			}
			if frappe.flags.get("pos_next_collect_perf"):
				frappe.flags.setdefault("pos_next_perf_records", []).append(payload)

			logger = frappe.logger(LOGGER_NAME, allow_site=True, file_count=5, max_size=1_000_000)
			# frappe.logger() defaults to ERROR, which silently drops warning() and info().
			log_all = bool(frappe.conf.get("pos_next_perf_log_all"))
			logger.setLevel(logging.INFO if log_all else logging.WARNING)
			line = json.dumps(payload, default=str)
			if total_ms >= slow_ms:
				logger.warning(line)
			elif log_all:
				logger.info(line)
		except Exception:
			# Instrumentation must never break a sale. Use the stdlib logger here:
			# frappe.logger() may be the very thing that just failed.
			logging.getLogger(LOGGER_NAME).exception("StepTimer failed to log")
		return total_ms
