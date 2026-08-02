# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta

import frappe
from frappe.utils import get_time, getdate, now_datetime

FROM_TIME_FIELD = "pos_active_from_time"
TO_TIME_FIELD = "pos_active_to_time"

SCHEDULE_FIELDS: tuple[str, ...] = (FROM_TIME_FIELD, TO_TIME_FIELD)


MIDNIGHT = "00:00:00"




def parse_time(value) -> dt_time | None:
	if value is None or value == "":
		return None
	if isinstance(value, dt_time):
		return value.replace(microsecond=0)
	if isinstance(value, timedelta):
		return (datetime.min + value).time().replace(microsecond=0)
	try:
		parsed = get_time(value)
	except Exception:
		return None
	return parsed.replace(microsecond=0) if parsed else None


def get_window(rule) -> tuple[dt_time | None, dt_time | None]:
	start = parse_time(rule.get(FROM_TIME_FIELD))
	end = parse_time(rule.get(TO_TIME_FIELD))
	if start is None or end is None:
		return None, None
	return start, end


def has_schedule(rule) -> bool:
	start, end = get_window(rule)
	return start is not None and start != end


# ---------------------------------------------------------------------------
# Python form
# ---------------------------------------------------------------------------


def time_matches(start: dt_time | None, end: dt_time | None, moment: dt_time) -> bool:
	if start is None or end is None:
		return True
	if start == end:
		return True  # all day
	if start < end:
		return start <= moment <= end
	return moment >= start or moment <= end


def is_active_at(rule, when: datetime | None = None) -> bool:
	"""Whether ``rule`` is live at ``when`` (system timezone; defaults to now)."""
	when = when or now_datetime()
	start, end = get_window(rule)
	return time_matches(start, end, when.time())


# ---------------------------------------------------------------------------
# SQL form
# ---------------------------------------------------------------------------


def build_sql_predicate(alias: str, values: dict, when: datetime | None = None) -> str:
	when = when or now_datetime()
	values["pos_schedule_time"] = when.time().strftime("%H:%M:%S")

	start_col = f"{alias}.{FROM_TIME_FIELD}"
	end_col = f"{alias}.{TO_TIME_FIELD}"

	return f"""
		and (
			{start_col} is null or {end_col} is null
			or {start_col} = {end_col}
			or ({start_col} < {end_col}
				and %(pos_schedule_time)s between {start_col} and {end_col})
			or ({start_col} > {end_col}
				and (%(pos_schedule_time)s >= {start_col}
					or %(pos_schedule_time)s <= {end_col}))
		)
	""".strip()


# ---------------------------------------------------------------------------
# Client form
# ---------------------------------------------------------------------------


def to_client_payload(rule) -> dict | None:

	if not has_schedule(rule):
		return None

	start, end = get_window(rule)
	return {
		"from_time": start.strftime("%H:%M:%S"),
		"to_time": end.strftime("%H:%M:%S"),
	}


def schedule_fields_available(doctype: str = "Pricing Rule") -> bool:
	cache = getattr(schedule_fields_available, "_cache", None)
	if cache is None:
		cache = schedule_fields_available._cache = {}

	key = (getattr(frappe.local, "site", None), doctype)
	if key in cache:
		return cache[key]

	try:
		result = frappe.db.has_column(doctype, FROM_TIME_FIELD)
	except Exception:
		result = False

	cache[key] = result
	return result


def filter_rules_by_schedule(rule_map, when: datetime | None = None) -> dict:
	if not rule_map or not schedule_fields_available():
		return rule_map

	windows = frappe.get_all(
		"Pricing Rule",
		filters={"name": ["in", list(rule_map.keys())]},
		fields=["name", *SCHEDULE_FIELDS],
	)
	scheduled = {row["name"]: row for row in windows if has_schedule(row)}
	if not scheduled:
		return rule_map

	when = when or now_datetime()
	return {
		name: details
		for name, details in rule_map.items()
		if name not in scheduled or is_active_at(scheduled[name], when)
	}


def normalize_schedule_fields(doc, method=None):
	if not schedule_fields_available(doc.doctype):
		return

	start = parse_time(doc.get(FROM_TIME_FIELD))
	end = parse_time(doc.get(TO_TIME_FIELD))

	if start is None or end is None:
		doc.set(FROM_TIME_FIELD, MIDNIGHT)
		doc.set(TO_TIME_FIELD, MIDNIGHT)
		return

	if doc.get("__islocal") and _seconds_apart(start, end) <= AUTOFILL_TOLERANCE_SECONDS:
		doc.set(FROM_TIME_FIELD, MIDNIGHT)
		doc.set(TO_TIME_FIELD, MIDNIGHT)

	if not doc.get("valid_from"):
		doc.set(FROM_TIME_FIELD, MIDNIGHT)
	if not doc.get("valid_upto"):
		doc.set(TO_TIME_FIELD, MIDNIGHT)


AUTOFILL_TOLERANCE_SECONDS = 5


def _seconds_apart(start: dt_time, end: dt_time) -> int:
	as_seconds = lambda t: t.hour * 3600 + t.minute * 60 + t.second  # noqa: E731
	return abs(as_seconds(start) - as_seconds(end))


def get_inactive_rules(rule_names, when: datetime | None = None) -> list[str]:
	"""Which of these Pricing Rules were outside their hour window at ``when``.

	Used as a submission guard. ``when`` should be the document's own posting
	moment, so an offline sale made inside the window and synced later is judged
	at the time of sale and not rejected.
	"""
	names = [name for name in (rule_names or []) if name]
	if not names or not schedule_fields_available():
		return []

	rows = frappe.get_all(
		"Pricing Rule",
		filters={"name": ["in", names]},
		fields=["name", *SCHEDULE_FIELDS],
	)
	when = when or now_datetime()
	return [row["name"] for row in rows if has_schedule(row) and not is_active_at(row, when)]


def resolve_moment(args=None) -> datetime:
	"""The moment a document should be judged at.

	Uses the document's own posting date/time when available, so an offline sale
	made inside the window and synced hours later is still judged at the time of
	sale rather than the time of sync. Falls back to now for a live cart.
	"""
	if not args:
		return now_datetime()

	posting_time = parse_time(args.get("posting_time"))
	if not posting_time:
		return now_datetime()

	posting_date = args.get("posting_date") or args.get("transaction_date")
	if not posting_date:
		return now_datetime()

	try:
		return datetime.combine(getdate(posting_date), posting_time)
	except Exception:
		return now_datetime()
