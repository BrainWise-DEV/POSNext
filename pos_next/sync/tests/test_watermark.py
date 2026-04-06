# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import now_datetime


def _cleanup():
	frappe.db.delete("Sync Watermark")
	frappe.db.delete("Sync Tombstone")
	frappe.db.commit()


def test_watermark_upsert():
	"""Watermark CRUD via upsert helper."""
	_cleanup()
	try:
		from pos_next.pos_next.doctype.sync_watermark.sync_watermark import SyncWatermark
		ts = now_datetime()
		row = SyncWatermark.upsert("Item", ts, records_pulled=10)
		assert row.doctype_name == "Item"
		assert row.records_pulled == 10

		ts2 = now_datetime()
		row2 = SyncWatermark.upsert("Item", ts2, records_pulled=5)
		assert row2.name == row.name, "upsert should update existing row, not create new"
		assert row2.records_pulled == 5
		print("PASS: test_watermark_upsert")
	finally:
		_cleanup()


def test_watermark_unique_per_doctype():
	"""Only one Sync Watermark row per DocType."""
	_cleanup()
	try:
		from pos_next.pos_next.doctype.sync_watermark.sync_watermark import SyncWatermark
		ts = now_datetime()
		SyncWatermark.upsert("Item", ts)
		SyncWatermark.upsert("Customer", ts)
		SyncWatermark.upsert("Item", ts)  # should update, not insert
		count = frappe.db.count("Sync Watermark")
		assert count == 2, f"Expected 2 rows (Item, Customer), got {count}"
		print("PASS: test_watermark_unique_per_doctype")
	finally:
		_cleanup()


def test_tombstone_record():
	"""Creating tombstones is simple."""
	_cleanup()
	try:
		from pos_next.pos_next.doctype.sync_tombstone.sync_tombstone import SyncTombstone
		t = SyncTombstone.record("Item", "ITEM-001")
		assert t.reference_doctype == "Item"
		assert t.reference_name == "ITEM-001"
		assert t.deleted_at is not None
		print("PASS: test_tombstone_record")
	finally:
		_cleanup()


def run_all():
	test_watermark_upsert()
	test_watermark_unique_per_doctype()
	test_tombstone_record()
	print("\nAll Watermark/Tombstone tests PASSED")
