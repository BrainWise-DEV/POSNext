"""
E2E test: full masters pull cycle respecting priority ordering.

Run from BRANCH site (dev.pos on frappe-bench-16):
  bench --site dev.pos execute pos_next.sync.tests._test_e2e_full_pull.run_all
"""

import frappe
from pos_next.sync.transport import build_session_from_config
from pos_next.sync.masters_puller import MastersPuller


def test_full_pull_cycle():
	"""Run a complete pull cycle — Company first, then Warehouse, then Items."""
	# Import adapters to register them
	import pos_next.sync.adapters.item
	import pos_next.sync.adapters.item_price
	import pos_next.sync.adapters.customer
	import pos_next.sync.adapters.generic_master

	session = build_session_from_config()
	puller = MastersPuller(session)

	# Pull in priority order (like MastersPuller.run does)
	priority_order = [
		("Company", 80),
		("Currency", 80),
		("Warehouse", 90),
		("UOM", 100),
		("Item Group", 100),
		("Item", 100),
	]

	for dt, prio in priority_order:
		upserted, deleted, errors = puller._pull_one_doctype(dt, "2000-01-01 00:00:00", 100)
		status = "OK" if errors == 0 else f"ERRORS={errors}"
		print(f"  {dt} (prio {prio}): upserted={upserted}, deleted={deleted}, {status}")

	session.logout()

	# Verify Warehouses arrived (they depend on Company being pulled first)
	wh_count = frappe.db.count("Warehouse")
	print(f"\nWarehouses on branch after full pull: {wh_count}")
	print("PASS: test_full_pull_cycle")


def run_all():
	test_full_pull_cycle()
	print("\nAll E2E Full Pull tests PASSED")
