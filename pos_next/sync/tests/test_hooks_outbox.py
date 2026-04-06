# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


def _cleanup():
	frappe.db.delete("Sync Outbox")
	frappe.db.commit()


def test_method_to_operation():
	"""Maps Frappe doc_event method names to outbox operations."""
	from pos_next.sync.hooks_outbox import _method_to_operation
	assert _method_to_operation("on_submit") == "submit"
	assert _method_to_operation("on_cancel") == "cancel"
	assert _method_to_operation("on_update") == "update"
	assert _method_to_operation("on_update_after_submit") == "update"
	assert _method_to_operation("after_insert") == "insert"
	assert _method_to_operation("on_trash") == "delete"
	print("PASS: test_method_to_operation")


def test_enqueue_guard():
	"""_is_branch_site returns a bool."""
	from pos_next.sync.hooks_outbox import _is_branch_site
	result = _is_branch_site()
	assert isinstance(result, bool)
	print("PASS: test_enqueue_guard")


def test_enqueue_creates_outbox_row():
	"""enqueue_to_outbox creates a Sync Outbox row when on a Branch site."""
	_cleanup()
	try:
		from pos_next.sync.hooks_outbox import _is_branch_site

		if not _is_branch_site():
			print("SKIP: test_enqueue_creates_outbox_row (not a Branch site)")
			return

		from pos_next.sync.hooks_outbox import enqueue_to_outbox
		from unittest.mock import MagicMock

		doc = MagicMock()
		doc.doctype = "Sales Invoice"
		doc.name = "TEST-SINV-001"
		doc.as_dict.return_value = {"name": "TEST-SINV-001", "total": 100}

		enqueue_to_outbox(doc, method="on_submit")

		count = frappe.db.count("Sync Outbox", {"reference_doctype": "Sales Invoice", "reference_name": "TEST-SINV-001"})
		assert count == 1, f"Expected 1 outbox row, got {count}"

		row = frappe.get_all(
			"Sync Outbox",
			filters={"reference_name": "TEST-SINV-001"},
			fields=["operation", "sync_status"],
		)[0]
		assert row.operation == "submit"
		assert row.sync_status == "pending"
		print("PASS: test_enqueue_creates_outbox_row")
	finally:
		_cleanup()


def run_all():
	test_method_to_operation()
	test_enqueue_guard()
	test_enqueue_creates_outbox_row()
	print("\nAll Outbox Hooks tests PASSED")
