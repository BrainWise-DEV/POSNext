# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.exceptions import ValidationError


def _cleanup():
	"""Remove all Sync Site Config rows (for test isolation)."""
	frappe.db.delete("Sync Site Config")
	frappe.db.commit()


def test_branch_is_singleton():
	"""A Branch-role Sync Site Config can only exist once per site."""
	_cleanup()
	try:
		doc1 = frappe.get_doc({
			"doctype": "Sync Site Config",
			"site_role": "Branch",
			"branch_code": "CAI",
			"enabled": 1,
			"central_url": "https://central.test",
			"sync_username": "sync@test.com",
			"sync_password": "secret123",
		})
		doc1.insert(ignore_permissions=True)

		doc2 = frappe.get_doc({
			"doctype": "Sync Site Config",
			"site_role": "Branch",
			"branch_code": "ALX",
			"enabled": 1,
			"central_url": "https://central.test",
			"sync_username": "sync2@test.com",
			"sync_password": "secret456",
		})

		raised = False
		try:
			doc2.insert(ignore_permissions=True)
		except ValidationError as e:
			raised = True
			assert "Branch" in str(e), f"Expected branch-singleton error, got: {e}"

		assert raised, "Second Branch-role config should have been rejected"
		print("PASS: test_branch_is_singleton")
	finally:
		_cleanup()


def test_central_allows_multiple():
	"""Central-role allows multiple Sync Site Config rows (one per branch)."""
	_cleanup()
	try:
		for code in ("CAI", "ALX", "HQ"):
			doc = frappe.get_doc({
				"doctype": "Sync Site Config",
				"site_role": "Central",
				"branch_code": code,
				"enabled": 1,
			})
			doc.insert(ignore_permissions=True)
		count = frappe.db.count("Sync Site Config")
		assert count == 3, f"Expected 3 Central rows, got {count}"
		print("PASS: test_central_allows_multiple")
	finally:
		_cleanup()


def test_branch_code_unique():
	"""branch_code must be unique across Sync Site Config rows."""
	_cleanup()
	try:
		doc1 = frappe.get_doc({
			"doctype": "Sync Site Config",
			"site_role": "Central",
			"branch_code": "CAI",
			"enabled": 1,
		})
		doc1.insert(ignore_permissions=True)

		doc2 = frappe.get_doc({
			"doctype": "Sync Site Config",
			"site_role": "Central",
			"branch_code": "CAI",
			"enabled": 1,
		})
		raised = False
		try:
			doc2.insert(ignore_permissions=True)
		except Exception:
			raised = True
		assert raised, "Duplicate branch_code should be rejected"
		print("PASS: test_branch_code_unique")
	finally:
		_cleanup()


def test_https_enforced():
	"""central_url must use https:// scheme."""
	_cleanup()
	try:
		doc = frappe.get_doc({
			"doctype": "Sync Site Config",
			"site_role": "Branch",
			"branch_code": "CAI",
			"enabled": 1,
			"central_url": "http://insecure.test",
			"sync_username": "sync@test.com",
			"sync_password": "secret",
		})
		raised = False
		try:
			doc.insert(ignore_permissions=True)
		except ValidationError as e:
			raised = True
			assert "https" in str(e).lower()
		assert raised, "http:// URL should have been rejected"
		print("PASS: test_https_enforced")
	finally:
		_cleanup()


def run_all():
	test_branch_is_singleton()
	test_central_allows_multiple()
	test_branch_code_unique()
	test_https_enforced()
	print("\nAll Sync Site Config tests PASSED")
