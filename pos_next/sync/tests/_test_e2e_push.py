"""
E2E: enqueue an outbox row on branch → drain to central → verify on central.

Run from BRANCH site (dev.pos on frappe-bench-16):
  bench --site dev.pos execute pos_next.sync.tests._test_e2e_push.run_all
"""

import frappe
import json
from pos_next.sync.transport import build_session_from_config
from pos_next.sync.outbox_drainer import OutboxDrainer
from pos_next.sync.masters_puller import _ensure_adapters_loaded


def test_push_outbox_to_central():
	"""Enqueue a fake outbox row and drain it to central."""
	_ensure_adapters_loaded()
	from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox

	# Clean up previous test rows
	frappe.db.delete("Sync Outbox", {"reference_name": "E2E-PUSH-TEST"})
	frappe.db.commit()

	# Enqueue a test row (Warehouse — simple, exists on central)
	SyncOutbox.enqueue(
		reference_doctype="Warehouse",
		reference_name="E2E-PUSH-TEST",
		operation="update",
		payload=json.dumps({"name": "E2E-PUSH-TEST", "warehouse_name": "E2E Push Test WH"}),
		priority=50,
	)

	# Drain to central
	session = build_session_from_config()
	branch_code = frappe.db.get_value("Sync Site Config", {"site_role": "Branch"}, "branch_code")
	drainer = OutboxDrainer(session, branch_code=branch_code)
	acked, failed, dead = drainer.drain()

	print(f"Drain result: acked={acked}, failed={failed}, dead={dead}")
	assert acked >= 1, f"Expected at least 1 acked, got {acked}"

	status = frappe.db.get_value("Sync Outbox", {"reference_name": "E2E-PUSH-TEST"}, "sync_status")
	assert status == "acked", f"Expected acked, got {status}"

	session.logout()
	print("PASS: test_push_outbox_to_central")


def run_all():
	test_push_outbox_to_central()
	print("\nAll E2E Push tests PASSED")
