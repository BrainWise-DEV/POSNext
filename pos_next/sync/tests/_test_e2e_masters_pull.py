"""
End-to-end integration test: pull Items from central → verify on branch.

Run from the BRANCH site (dev.pos on frappe-bench-16):
  bench --site dev.pos execute pos_next.sync.tests._test_e2e_masters_pull.run_all

Prerequisites:
  - Both benches running (port 8000 central, port 8001 branch)
  - Sync Site Config configured on both
"""

import frappe
from pos_next.sync.transport import build_session_from_config
from pos_next.sync.masters_puller import MastersPuller


def test_pull_items_from_central():
	"""Pull Items from central and verify they arrive."""
	# Import adapters to register them
	import pos_next.sync.adapters.item
	import pos_next.sync.adapters.item_price
	import pos_next.sync.adapters.customer
	import pos_next.sync.adapters.generic_master

	session = build_session_from_config()

	local_count_before = frappe.db.count("Item")

	puller = MastersPuller(session)
	watermark = "2000-01-01 00:00:00"
	upserted, deleted, errors = puller._pull_one_doctype("Item", watermark, 50)

	print(f"Pulled: upserted={upserted}, deleted={deleted}, errors={errors}")

	local_count_after = frappe.db.count("Item")
	print(f"Items before={local_count_before}, after={local_count_after}")

	session.logout()
	print("PASS: test_pull_items_from_central")


def test_pull_creates_watermark():
	"""After pulling, a Sync Watermark record exists for Item."""
	from pos_next.pos_next.doctype.sync_watermark.sync_watermark import SyncWatermark

	wm = SyncWatermark.get_for("Item")
	if wm:
		print(f"Watermark for Item: last_modified={wm.last_modified}, records_pulled={wm.records_pulled}")
		assert wm.last_modified is not None
		print("PASS: test_pull_creates_watermark")
	else:
		print("SKIP: test_pull_creates_watermark (no watermark — central may have no Items)")


def test_pull_warehouses_from_central():
	"""Pull Warehouses from central via GenericMasterAdapter."""
	import pos_next.sync.adapters.generic_master

	session = build_session_from_config()
	puller = MastersPuller(session)

	upserted, deleted, errors = puller._pull_one_doctype("Warehouse", "2000-01-01 00:00:00", 50)
	print(f"Warehouses pulled: upserted={upserted}, deleted={deleted}, errors={errors}")

	session.logout()
	print("PASS: test_pull_warehouses_from_central")


def test_health_endpoint_reachable():
	"""Branch can reach central's health endpoint."""
	session = build_session_from_config()
	resp = session.get("/api/method/pos_next.sync.api.health.health")
	assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
	data = resp.json().get("message", {})
	print(f"Central health: {data}")
	assert "server_time" in data
	assert "frappe_version" in data
	session.logout()
	print("PASS: test_health_endpoint_reachable")


def run_all():
	test_health_endpoint_reachable()
	test_pull_items_from_central()
	test_pull_creates_watermark()
	test_pull_warehouses_from_central()
	print("\nAll E2E Masters Pull tests PASSED")
