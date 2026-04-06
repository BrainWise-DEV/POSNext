# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Conflict resolution strategies."""

from pos_next.sync.defaults import CONFLICT_RULES
from pos_next.sync.exceptions import SyncConflictError


def resolve(local, incoming, rule):
	"""
	Apply a conflict resolution rule to two payloads.

	Returns (winner_payload, verdict) where verdict is one of:
	  "local", "incoming", "merged".

	Raises:
	  SyncConflictError if rule is "Manual".
	  ValueError if rule is not recognized.
	"""
	if rule not in CONFLICT_RULES:
		raise ValueError(f"Unknown conflict rule: {rule}")

	if rule == "Manual":
		raise SyncConflictError(
			f"Manual resolution required for {incoming.get('name', '<unnamed>')}"
		)

	if rule == "Central-Wins":
		return incoming, "incoming"

	if rule == "Branch-Wins":
		return incoming, "incoming"

	if rule == "Last-Write-Wins":
		local_ts = str(local.get("modified") or "")
		incoming_ts = str(incoming.get("modified") or "")
		if incoming_ts >= local_ts:
			return incoming, "incoming"
		return local, "local"

	if rule == "Field-Level-LWW":
		return _merge_field_level(local, incoming), "merged"

	raise ValueError(f"Unimplemented conflict rule: {rule}")


def _merge_field_level(local, incoming):
	"""
	Merge two payloads field-by-field based on per-field timestamps.

	Both payloads must carry a `__field_ts` dict mapping fieldname → timestamp.
	For each field, the value from whichever payload has the newer timestamp wins.
	Fields with no timestamp entry default to local's value.
	"""
	local_ts = local.get("__field_ts", {}) or {}
	incoming_ts = incoming.get("__field_ts", {}) or {}

	merged = dict(local)
	all_fields = set(local.keys()) | set(incoming.keys())
	all_fields.discard("__field_ts")

	for field in all_fields:
		l_ts = str(local_ts.get(field, ""))
		i_ts = str(incoming_ts.get(field, ""))
		if i_ts and i_ts > l_ts:
			merged[field] = incoming.get(field)

	# Merge the timestamp maps too — keep max per field
	merged_ts = dict(local_ts)
	for f, ts in incoming_ts.items():
		if str(ts) > str(merged_ts.get(f, "")):
			merged_ts[f] = ts
	merged["__field_ts"] = merged_ts
	return merged
