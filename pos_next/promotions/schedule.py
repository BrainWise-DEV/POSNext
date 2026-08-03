# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt
"""Evaluate promotion validity with minute-level precision.

While ERPNext natively gates promotions by whole days, this logic adds a time 
component to both ends of the date range to create a single, continuous span:

* ``start`` = ``valid_from`` + ``Active From Time`` (defaults to 00:00:00, or midnight)
* ``end`` = ``valid_upto`` + ``Active To Time`` (defaults to 00:00:00, evaluated as end-of-day)

The time components act as absolute boundaries for the first and last days of the 
promotion; they do not represent a daily repeating schedule. For example, a promotion 
valid until tomorrow at 01:08 remains active today at 02:08.

This time-bound logic is strictly enforced on the POS path via:
* :func:`filter_rules_by_schedule`: Evaluates available offers.
* :func:`get_inactive_rules`: Acts as a guard during sale submission.

Documents created via the Desk retain ERPNext's default whole-day behaviour.

Note:
    All chronological comparisons are evaluated strictly in the system timezone, 
    ignoring the client's timezone.
"""

from __future__ import annotations

from datetime import date as dt_date, datetime, time as dt_time, timedelta

import frappe
from frappe.utils import get_time, getdate, now_datetime

FROM_TIME_FIELD = "pos_active_from_time"
TO_TIME_FIELD = "pos_active_to_time"
FROM_DATE_FIELD = "valid_from"
TO_DATE_FIELD = "valid_upto"

SCHEDULE_FIELDS: tuple[str, ...] = (
	FROM_DATE_FIELD,
	TO_DATE_FIELD,
	FROM_TIME_FIELD,
	TO_TIME_FIELD,
)

#: The unset value for both time fields. On the start date it means "from
#: midnight"; on the end date it means "to the end of the day", so that
#: ``valid_upto`` stays inclusive exactly as ERPNext treats it.
MIDNIGHT = "00:00:00"

END_OF_DAY = dt_time(23, 59, 59)

AUTOFILL_TOLERANCE_SECONDS = 5


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


def _parse_date(value) -> dt_date | None:
	if not value:
		return None
	try:
		return getdate(value)
	except Exception:
		return None


def get_period(rule) -> tuple[datetime | None, datetime | None]:
	"""The ``(start, end)`` instants a rule is live between.

	``None`` at either end means unbounded in that direction. A blank or midnight
	Active To Time keeps the last day whole rather than ending it at 00:00:00.
	"""
	start_date = _parse_date(rule.get(FROM_DATE_FIELD))
	end_date = _parse_date(rule.get(TO_DATE_FIELD))

	start = None
	if start_date:
		start = datetime.combine(start_date, parse_time(rule.get(FROM_TIME_FIELD)) or dt_time.min)

	end = None
	if end_date:
		end_time = parse_time(rule.get(TO_TIME_FIELD))
		if end_time is None or end_time == dt_time.min:
			end_time = END_OF_DAY
		end = datetime.combine(end_date, end_time)

	return start, end


def is_active_at(rule, when: datetime | None = None) -> bool:
	"""Whether ``rule`` is live at ``when`` (system timezone; defaults to now)."""
	when = when or now_datetime()
	start, end = get_period(rule)
	if start and when < start:
		return False
	if end and when > end:
		return False
	return True


def has_time_bound(rule) -> bool:
	"""Whether either end carries a time that narrows its day."""
	start_time = parse_time(rule.get(FROM_TIME_FIELD))
	end_time = parse_time(rule.get(TO_TIME_FIELD))
	return bool(
		(start_time and start_time != dt_time.min and rule.get(FROM_DATE_FIELD))
		or (end_time and end_time != dt_time.min and rule.get(TO_DATE_FIELD))
	)


def to_client_payload(rule) -> dict | None:
	"""The period the offline cart needs to judge a rule itself.

	``None`` when neither end carries a time, since the cart already honours the
	plain date range — this keeps the field absent for almost every rule.
	"""
	if not has_time_bound(rule):
		return None

	start, end = get_period(rule)
	return {
		"start": start.isoformat(sep=" ") if start else None,
		"end": end.isoformat(sep=" ") if end else None,
	}


def schedule_fields_available(doctype: str = "Pricing Rule") -> bool:
	"""Whether this site has migrated the schedule custom fields yet.

	The engine patch is process-wide across every site on the bench, but only
	sites with POS Next installed have these columns. Cached per site per worker.
	"""
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


def _fetch_periods(rule_names) -> dict:
	names = [name for name in (rule_names or []) if name]
	if not names or not schedule_fields_available():
		return {}
	return {
		row["name"]: row
		for row in frappe.get_all(
			"Pricing Rule", filters={"name": ["in", names]}, fields=["name", *SCHEDULE_FIELDS]
		)
	}


def filter_rules_by_schedule(rule_map, when: datetime | None = None) -> dict:
	"""Drop rules whose validity period excludes ``when``.

	The POS needs its own check: transaction-scope rules and explicitly selected
	offers are read straight from the table, so they never pass the engine's gate.
	"""
	periods = _fetch_periods(rule_map.keys()) if rule_map else {}
	if not periods:
		return rule_map

	when = when or now_datetime()
	return {
		name: details
		for name, details in rule_map.items()
		if name not in periods or is_active_at(periods[name], when)
	}


def get_inactive_rules(rule_names, when: datetime | None = None) -> list[str]:
	"""Which of these Pricing Rules were outside their validity period at ``when``.

	A submission guard. ``when`` is the document's own posting moment, so an
	offline sale made inside the period and synced later is judged at the time of
	sale rather than rejected.
	"""
	periods = _fetch_periods(rule_names)
	when = when or now_datetime()
	return [name for name, row in periods.items() if not is_active_at(row, when)]


def resolve_moment(args=None) -> datetime:
	"""The moment a document should be judged at.

	Prefers the document's own posting date/time, so an offline sale synced hours
	later is judged when it happened. Falls back to now for a live cart.
	"""
	if not args:
		return now_datetime()

	posting_time = parse_time(args.get("posting_time"))
	posting_date = _parse_date(args.get("posting_date") or args.get("transaction_date"))
	if not posting_time or not posting_date:
		return now_datetime()

	return datetime.combine(posting_date, posting_time)


def normalize_schedule_fields(doc, method=None):
	if not schedule_fields_available(doc.doctype):
		return

	start_time = parse_time(doc.get(FROM_TIME_FIELD))
	end_time = parse_time(doc.get(TO_TIME_FIELD))

	# The auto-fill is only recognisable as a *pair*, so collapse it before either
	# end is cleared for a missing date.
	autofilled = (
		doc.get("__islocal")
		and start_time
		and end_time
		and _seconds_apart(start_time, end_time) <= AUTOFILL_TOLERANCE_SECONDS
	)
	if autofilled or start_time is None:
		doc.set(FROM_TIME_FIELD, MIDNIGHT)
	if autofilled or end_time is None:
		doc.set(TO_TIME_FIELD, MIDNIGHT)

	if not doc.get(FROM_DATE_FIELD):
		doc.set(FROM_TIME_FIELD, MIDNIGHT)
	if not doc.get(TO_DATE_FIELD):
		doc.set(TO_TIME_FIELD, MIDNIGHT)


def _seconds_apart(start: dt_time, end: dt_time) -> int:
	def as_seconds(value: dt_time) -> int:
		return value.hour * 3600 + value.minute * 60 + value.second

	return abs(as_seconds(start) - as_seconds(end))
