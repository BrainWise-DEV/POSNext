# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


def _cleanup():
	frappe.db.delete("Sync Outbox")
	frappe.db.commit()


def test_insert_creates_row():
	"""Creating an outbox row is straightforward."""
	_cleanup()
	try:
		from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox
		row = SyncOutbox.enqueue(
			reference_doctype="Sales Invoice",
			reference_name="SINV-CAI-2026-00001",
			operation="insert",
			payload='{"name":"SINV-CAI-2026-00001","total":100}',
			priority=50,
		)
		assert row.sync_status == "pending"
		assert row.attempts == 0
		print("PASS: test_insert_creates_row")
	finally:
		_cleanup()


def test_compaction_on_update():
	"""Multiple updates to same (doctype, name, 'update') collapse to one pending row."""
	_cleanup()
	try:
		from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox
		SyncOutbox.enqueue(
			reference_doctype="Customer",
			reference_name="Walk-In Cairo",
			operation="update",
			payload='{"name":"Walk-In Cairo","v":1}',
			priority=50,
		)
		SyncOutbox.enqueue(
			reference_doctype="Customer",
			reference_name="Walk-In Cairo",
			operation="update",
			payload='{"name":"Walk-In Cairo","v":2}',
			priority=50,
		)
		SyncOutbox.enqueue(
			reference_doctype="Customer",
			reference_name="Walk-In Cairo",
			operation="update",
			payload='{"name":"Walk-In Cairo","v":3}',
			priority=50,
		)
		count = frappe.db.count(
			"Sync Outbox",
			{"reference_doctype": "Customer", "reference_name": "Walk-In Cairo", "sync_status": "pending"},
		)
		assert count == 1, f"Expected 1 compacted row, got {count}"

		payload = frappe.db.get_value(
			"Sync Outbox",
			{"reference_doctype": "Customer", "reference_name": "Walk-In Cairo"},
			"payload",
		)
		assert '"v":3' in payload, f"Latest payload should win, got: {payload}"
		print("PASS: test_compaction_on_update")
	finally:
		_cleanup()


def test_terminal_ops_always_insert():
	"""submit/cancel/delete never compact — they always insert new rows."""
	_cleanup()
	try:
		from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox
		for op in ("submit", "cancel", "delete"):
			SyncOutbox.enqueue(
				reference_doctype="Sales Invoice",
				reference_name="SINV-CAI-2026-00001",
				operation=op,
				payload='{"name":"SINV-CAI-2026-00001"}',
				priority=50,
			)
		count = frappe.db.count(
			"Sync Outbox",
			{"reference_doctype": "Sales Invoice", "reference_name": "SINV-CAI-2026-00001"},
		)
		assert count == 3, f"Expected 3 terminal rows, got {count}"
		print("PASS: test_terminal_ops_always_insert")
	finally:
		_cleanup()


def test_acked_row_not_compacted():
	"""An acked row is ignored by compaction; new update creates a fresh pending row."""
	_cleanup()
	try:
		from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox
		row = SyncOutbox.enqueue(
			reference_doctype="Customer",
			reference_name="C1",
			operation="update",
			payload='{"v":1}',
			priority=50,
		)
		# Simulate successful sync
		frappe.db.set_value("Sync Outbox", row.name, "sync_status", "acked")
		frappe.db.commit()

		SyncOutbox.enqueue(
			reference_doctype="Customer",
			reference_name="C1",
			operation="update",
			payload='{"v":2}',
			priority=50,
		)
		pending = frappe.db.count(
			"Sync Outbox",
			{"reference_doctype": "Customer", "reference_name": "C1", "sync_status": "pending"},
		)
		acked = frappe.db.count(
			"Sync Outbox",
			{"reference_doctype": "Customer", "reference_name": "C1", "sync_status": "acked"},
		)
		assert pending == 1 and acked == 1, f"Expected pending=1, acked=1, got pending={pending}, acked={acked}"
		print("PASS: test_acked_row_not_compacted")
	finally:
		_cleanup()


def run_all():
	test_insert_creates_row()
	test_compaction_on_update()
	test_terminal_ops_always_insert()
	test_acked_row_not_compacted()
	print("\nAll Sync Outbox tests PASSED")
