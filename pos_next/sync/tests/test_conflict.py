# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from datetime import datetime


def test_last_write_wins_incoming_newer():
	from pos_next.sync.conflict import resolve
	local = {"name": "X", "v": 1, "modified": "2026-04-05 10:00:00"}
	incoming = {"name": "X", "v": 2, "modified": "2026-04-05 11:00:00"}
	winner, verdict = resolve(local, incoming, "Last-Write-Wins")
	assert winner is incoming
	assert verdict == "incoming"
	print("PASS: test_last_write_wins_incoming_newer")


def test_last_write_wins_local_newer():
	from pos_next.sync.conflict import resolve
	local = {"name": "X", "v": 1, "modified": "2026-04-05 12:00:00"}
	incoming = {"name": "X", "v": 2, "modified": "2026-04-05 11:00:00"}
	winner, verdict = resolve(local, incoming, "Last-Write-Wins")
	assert winner is local
	assert verdict == "local"
	print("PASS: test_last_write_wins_local_newer")


def test_last_write_wins_tie_goes_to_incoming():
	from pos_next.sync.conflict import resolve
	ts = "2026-04-05 10:00:00"
	local = {"name": "X", "v": 1, "modified": ts}
	incoming = {"name": "X", "v": 2, "modified": ts}
	winner, verdict = resolve(local, incoming, "Last-Write-Wins")
	assert winner is incoming
	print("PASS: test_last_write_wins_tie_goes_to_incoming")


def test_central_wins():
	from pos_next.sync.conflict import resolve
	local = {"name": "X", "v": 1}
	incoming = {"name": "X", "v": 2}
	winner, verdict = resolve(local, incoming, "Central-Wins")
	assert winner is incoming
	assert verdict == "incoming"
	print("PASS: test_central_wins")


def test_branch_wins():
	from pos_next.sync.conflict import resolve
	local = {"name": "X", "v": 1}
	incoming = {"name": "X", "v": 2}
	winner, verdict = resolve(local, incoming, "Branch-Wins")
	assert winner is incoming
	assert verdict == "incoming"
	print("PASS: test_branch_wins")


def test_manual_rule_raises():
	from pos_next.sync.conflict import resolve
	from pos_next.sync.exceptions import SyncConflictError
	local = {"name": "X", "v": 1}
	incoming = {"name": "X", "v": 2}
	raised = False
	try:
		resolve(local, incoming, "Manual")
	except SyncConflictError:
		raised = True
	assert raised, "Manual rule should raise SyncConflictError"
	print("PASS: test_manual_rule_raises")


def test_field_level_lww_merges_per_field():
	from pos_next.sync.conflict import resolve
	local = {
		"name": "X",
		"field_a": "local-a",
		"field_b": "local-b",
		"__field_ts": {"field_a": "2026-04-05 10:00:00", "field_b": "2026-04-05 12:00:00"},
	}
	incoming = {
		"name": "X",
		"field_a": "incoming-a",
		"field_b": "incoming-b",
		"__field_ts": {"field_a": "2026-04-05 11:00:00", "field_b": "2026-04-05 11:00:00"},
	}
	winner, verdict = resolve(local, incoming, "Field-Level-LWW")
	assert verdict == "merged"
	assert winner["field_a"] == "incoming-a"  # incoming had newer ts
	assert winner["field_b"] == "local-b"     # local had newer ts
	print("PASS: test_field_level_lww_merges_per_field")


def test_unknown_rule_raises():
	from pos_next.sync.conflict import resolve
	raised = False
	try:
		resolve({}, {}, "NotARealRule")
	except ValueError:
		raised = True
	assert raised
	print("PASS: test_unknown_rule_raises")


def run_all():
	test_last_write_wins_incoming_newer()
	test_last_write_wins_local_newer()
	test_last_write_wins_tie_goes_to_incoming()
	test_central_wins()
	test_branch_wins()
	test_manual_rule_raises()
	test_field_level_lww_merges_per_field()
	test_unknown_rule_raises()
	print("\nAll Conflict tests PASSED")
