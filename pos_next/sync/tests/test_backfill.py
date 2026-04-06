# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


TARGET_DOCTYPES = [
	"Sales Invoice",
	"Payment Entry",
	"Stock Ledger Entry",
	"POS Opening Shift",
	"POS Closing Shift",
	"Customer",
]


def test_no_null_sync_uuids_after_backfill():
	"""After the backfill runs, no rows in target DocTypes have NULL sync_uuid."""
	from pos_next.patches.v2_0_0.backfill_sync_uuid import execute

	execute()  # idempotent

	for dt in TARGET_DOCTYPES:
		total = frappe.db.count(dt)
		if total == 0:
			continue
		null_count = frappe.db.sql(
			f"SELECT COUNT(*) FROM `tab{dt}` WHERE sync_uuid IS NULL OR sync_uuid = ''"
		)[0][0]
		assert null_count == 0, f"{dt}: {null_count} rows have NULL sync_uuid"
	print("PASS: test_no_null_sync_uuids_after_backfill")


def test_backfill_is_idempotent():
	"""Running the backfill twice does not change existing UUIDs."""
	from pos_next.patches.v2_0_0.backfill_sync_uuid import execute

	execute()
	rows_before = frappe.db.sql(
		"SELECT name, sync_uuid FROM `tabCustomer` WHERE sync_uuid IS NOT NULL LIMIT 5",
		as_dict=True,
	)
	execute()
	rows_after = frappe.db.sql(
		"SELECT name, sync_uuid FROM `tabCustomer` WHERE sync_uuid IS NOT NULL LIMIT 5",
		as_dict=True,
	)
	before = {r.name: r.sync_uuid for r in rows_before}
	after = {r.name: r.sync_uuid for r in rows_after}
	for name, uuid_val in before.items():
		assert after.get(name) == uuid_val, f"Customer {name}: uuid changed"
	print("PASS: test_backfill_is_idempotent")


def run_all():
	test_no_null_sync_uuids_after_backfill()
	test_backfill_is_idempotent()
	print("\nAll Backfill tests PASSED")
