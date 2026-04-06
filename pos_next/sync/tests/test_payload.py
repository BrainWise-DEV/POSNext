# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


def test_compute_hash_stable():
	"""Same payload (order-independent) produces same hash."""
	from pos_next.sync.payload import compute_hash
	a = {"name": "ITEM-001", "item_name": "Apple", "price": 100}
	b = {"price": 100, "name": "ITEM-001", "item_name": "Apple"}
	assert compute_hash(a) == compute_hash(b)
	print("PASS: test_compute_hash_stable")


def test_compute_hash_different_on_change():
	from pos_next.sync.payload import compute_hash
	a = {"name": "ITEM-001", "price": 100}
	b = {"name": "ITEM-001", "price": 101}
	assert compute_hash(a) != compute_hash(b)
	print("PASS: test_compute_hash_different_on_change")


def test_compute_hash_ignores_meta_fields():
	"""modified, modified_by, owner, creation are excluded from hash."""
	from pos_next.sync.payload import compute_hash
	a = {"name": "ITEM-001", "price": 100, "modified": "2026-04-05 10:00:00", "modified_by": "a@x.com"}
	b = {"name": "ITEM-001", "price": 100, "modified": "2026-04-05 11:00:00", "modified_by": "b@x.com"}
	assert compute_hash(a) == compute_hash(b)
	print("PASS: test_compute_hash_ignores_meta_fields")


def test_strip_meta():
	"""strip_meta removes server-side meta fields."""
	from pos_next.sync.payload import strip_meta
	payload = {
		"name": "ITEM-001",
		"price": 100,
		"modified": "2026-04-05",
		"modified_by": "a@x.com",
		"owner": "admin",
		"creation": "2026-01-01",
		"docstatus": 0,
	}
	stripped = strip_meta(payload)
	assert "modified" not in stripped
	assert "modified_by" not in stripped
	assert "owner" not in stripped
	assert "creation" not in stripped
	assert stripped["name"] == "ITEM-001"
	assert stripped["price"] == 100
	assert "docstatus" in stripped  # docstatus is kept — it's semantic
	print("PASS: test_strip_meta")


def run_all():
	test_compute_hash_stable()
	test_compute_hash_different_on_change()
	test_compute_hash_ignores_meta_fields()
	test_strip_meta()
	print("\nAll Payload tests PASSED")
