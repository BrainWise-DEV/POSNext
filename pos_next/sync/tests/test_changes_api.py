# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
import json


def _cleanup():
	frappe.db.delete("Sync Tombstone")
	frappe.db.commit()


def test_changes_since_returns_upserts():
	"""changes_since returns records modified after the given watermark."""
	from pos_next.sync.api.changes import changes_since

	# Use a DocType that definitely has rows — DocType itself
	result = changes_since(doctype="DocType", since="2000-01-01 00:00:00", limit=5)
	assert "upserts" in result
	assert "tombstones" in result
	assert "next_since" in result
	assert "has_more" in result
	assert len(result["upserts"]) <= 5
	assert isinstance(result["upserts"], list)
	if result["upserts"]:
		assert "name" in result["upserts"][0]
		assert "modified" in result["upserts"][0]
	print("PASS: test_changes_since_returns_upserts")


def test_changes_since_pagination():
	"""has_more=True when more records exist beyond the limit."""
	from pos_next.sync.api.changes import changes_since

	result = changes_since(doctype="DocType", since="2000-01-01 00:00:00", limit=2)
	# There are certainly more than 2 DocTypes
	assert result["has_more"] is True
	assert len(result["upserts"]) == 2
	assert result["next_since"] is not None
	print("PASS: test_changes_since_pagination")


def test_changes_since_includes_tombstones():
	"""Tombstones for the given doctype are included."""
	_cleanup()
	try:
		from pos_next.sync.api.changes import changes_since
		from pos_next.pos_next.doctype.sync_tombstone.sync_tombstone import SyncTombstone

		SyncTombstone.record("Item", "FAKE-ITEM-001")
		SyncTombstone.record("Item", "FAKE-ITEM-002")
		SyncTombstone.record("Customer", "FAKE-CUST-001")  # different doctype

		result = changes_since(doctype="Item", since="2000-01-01 00:00:00", limit=100)
		item_tombstones = [t for t in result["tombstones"] if t["reference_name"].startswith("FAKE-ITEM")]
		assert len(item_tombstones) == 2, f"Expected 2 Item tombstones, got {len(item_tombstones)}"

		# Customer tombstone should NOT appear in Item query
		cust_tombstones = [t for t in result["tombstones"] if t["reference_name"].startswith("FAKE-CUST")]
		assert len(cust_tombstones) == 0
		print("PASS: test_changes_since_includes_tombstones")
	finally:
		_cleanup()


def test_changes_since_empty_result():
	"""Future watermark returns empty result."""
	from pos_next.sync.api.changes import changes_since

	result = changes_since(doctype="DocType", since="2099-01-01 00:00:00", limit=100)
	assert len(result["upserts"]) == 0
	assert result["has_more"] is False
	print("PASS: test_changes_since_empty_result")


def run_all():
	test_changes_since_returns_upserts()
	test_changes_since_pagination()
	test_changes_since_includes_tombstones()
	test_changes_since_empty_result()
	print("\nAll changes_since API tests PASSED")
