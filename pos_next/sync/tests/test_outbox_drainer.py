# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from unittest.mock import MagicMock


def _cleanup():
	frappe.db.delete("Sync Outbox")
	frappe.db.delete("Sync Dead Letter")
	frappe.db.commit()


def test_push_if_due_noop_without_branch():
	"""push_if_due does nothing when no Branch config exists or not due."""
	from pos_next.sync.outbox_drainer import push_if_due
	push_if_due()
	print("PASS: test_push_if_due_noop_without_branch")


def test_drainer_processes_pending_rows():
	"""OutboxDrainer sends pending outbox rows to central."""
	_cleanup()
	try:
		from pos_next.sync.outbox_drainer import OutboxDrainer
		from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox

		SyncOutbox.enqueue(
			reference_doctype="Sales Invoice",
			reference_name="TEST-SINV-DRAIN",
			operation="submit",
			payload='{"name":"TEST-SINV-DRAIN","docstatus":1}',
			priority=50,
		)

		fake_session = MagicMock()
		fake_resp = MagicMock()
		fake_resp.status_code = 200
		fake_resp.json.return_value = {
			"message": {"results": [{"name": "TEST-SINV-DRAIN", "sync_uuid": "", "status": "ok"}]}
		}
		fake_session.post.return_value = fake_resp

		drainer = OutboxDrainer(fake_session, branch_code="CAI")
		acked, failed, dead = drainer.drain()

		assert acked >= 1, f"Expected at least 1 acked, got {acked}"
		status = frappe.db.get_value("Sync Outbox", {"reference_name": "TEST-SINV-DRAIN"}, "sync_status")
		assert status == "acked", f"Expected acked, got {status}"
		print("PASS: test_drainer_processes_pending_rows")
	finally:
		_cleanup()


def test_drainer_handles_failure():
	"""On failure, outbox row gets attempts incremented."""
	_cleanup()
	try:
		from pos_next.sync.outbox_drainer import OutboxDrainer
		from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox

		SyncOutbox.enqueue(
			reference_doctype="Sales Invoice",
			reference_name="TEST-SINV-FAIL",
			operation="submit",
			payload='{"name":"TEST-SINV-FAIL"}',
			priority=50,
		)

		fake_session = MagicMock()
		fake_resp = MagicMock()
		fake_resp.status_code = 200
		fake_resp.json.return_value = {
			"message": {"results": [{"name": "TEST-SINV-FAIL", "sync_uuid": "", "status": "error", "error": "test error"}]}
		}
		fake_session.post.return_value = fake_resp

		drainer = OutboxDrainer(fake_session, branch_code="CAI")
		acked, failed, dead = drainer.drain()

		assert failed >= 1
		row = frappe.get_all(
			"Sync Outbox",
			filters={"reference_name": "TEST-SINV-FAIL"},
			fields=["sync_status", "attempts", "last_error"],
		)[0]
		assert row.sync_status == "failed"
		assert row.attempts == 1
		assert "test error" in (row.last_error or "")
		print("PASS: test_drainer_handles_failure")
	finally:
		_cleanup()


def test_drainer_dead_letters():
	"""After MAX_ATTEMPTS, row moves to dead letter."""
	_cleanup()
	try:
		from pos_next.sync.outbox_drainer import OutboxDrainer
		from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox
		from pos_next.sync.defaults import MAX_ATTEMPTS_BEFORE_DEAD

		row = SyncOutbox.enqueue(
			reference_doctype="Sales Invoice",
			reference_name="TEST-SINV-DEAD",
			operation="submit",
			payload='{"name":"TEST-SINV-DEAD"}',
			priority=50,
		)
		frappe.db.set_value("Sync Outbox", row.name, {
			"attempts": MAX_ATTEMPTS_BEFORE_DEAD,
			"sync_status": "failed",
		})
		frappe.db.commit()

		fake_session = MagicMock()
		fake_resp = MagicMock()
		fake_resp.status_code = 200
		fake_resp.json.return_value = {
			"message": {"results": [{"name": "TEST-SINV-DEAD", "sync_uuid": "", "status": "error", "error": "persistent"}]}
		}
		fake_session.post.return_value = fake_resp

		drainer = OutboxDrainer(fake_session, branch_code="CAI")
		acked, failed, dead = drainer.drain()

		assert dead >= 1
		assert not frappe.db.exists("Sync Outbox", {"reference_name": "TEST-SINV-DEAD"})
		assert frappe.db.exists("Sync Dead Letter", {"reference_name": "TEST-SINV-DEAD"})
		print("PASS: test_drainer_dead_letters")
	finally:
		_cleanup()
		frappe.db.delete("Sync Dead Letter")
		frappe.db.commit()


def run_all():
	test_push_if_due_noop_without_branch()
	test_drainer_processes_pending_rows()
	test_drainer_handles_failure()
	test_drainer_dead_letters()
	print("\nAll OutboxDrainer tests PASSED")
