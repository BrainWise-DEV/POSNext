# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
import json


def _cleanup():
	frappe.db.delete("Sync Record State")
	frappe.db.commit()


def test_ingest_returns_results():
	"""Ingest endpoint returns per-record results."""
	from pos_next.sync.api.ingest import ingest

	result = ingest(
		doctype="Warehouse",
		branch_code="CAI",
		records=json.dumps([
			{"operation": "update", "payload": {"name": "FAKE-WH-INGEST", "warehouse_name": "Test"}},
		]),
	)
	assert "results" in result
	assert len(result["results"]) == 1
	assert "name" in result["results"][0]
	assert "status" in result["results"][0]
	print("PASS: test_ingest_returns_results")


def test_ingest_empty_records():
	"""Empty records list returns empty results."""
	from pos_next.sync.api.ingest import ingest
	result = ingest(doctype="Warehouse", branch_code="CAI", records=json.dumps([]))
	assert result["results"] == []
	print("PASS: test_ingest_empty_records")


def run_all():
	test_ingest_returns_results()
	test_ingest_empty_records()
	print("\nAll Ingest API tests PASSED")
