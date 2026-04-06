# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


def _cleanup():
	for name in frappe.get_all("Customer", filters={"name": ("like", "SYNCTEST-%")}, pluck="name"):
		frappe.delete_doc("Customer", name, force=True, ignore_permissions=True)
	frappe.db.commit()


def _get_customer_defaults():
	"""Get customer_group and territory for test fixtures."""
	cg = frappe.db.get_single_value("Selling Settings", "customer_group") or frappe.db.get_value("Customer Group", {}, "name") or "All Customer Groups"
	territory = frappe.db.get_single_value("Selling Settings", "territory") or frappe.db.get_value("Territory", {}, "name") or "All Territories"
	return cg, territory


def test_customer_adapter_registered():
	"""CustomerAdapter is registered for 'Customer'."""
	from pos_next.sync.adapters import customer  # triggers registration
	from pos_next.sync import registry
	adapter = registry.get_adapter("Customer")
	assert adapter is not None
	assert adapter.doctype == "Customer"
	print("PASS: test_customer_adapter_registered")


def test_customer_adapter_conflict_key():
	"""Conflict key is mobile_no for dedup."""
	from pos_next.sync.adapters.customer import CustomerAdapter
	adapter = CustomerAdapter()
	assert adapter.conflict_key({"mobile_no": "01234567890"}) == ("mobile_no",)
	print("PASS: test_customer_adapter_conflict_key")


def test_customer_adapter_dedup_by_mobile():
	"""If a customer with same mobile_no exists under a different name, return existing."""
	_cleanup()
	try:
		from pos_next.sync.adapters.customer import CustomerAdapter
		adapter = CustomerAdapter()
		cg, territory = _get_customer_defaults()

		local = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": "SYNCTEST-Local Guy",
			"customer_type": "Individual",
			"customer_group": cg,
			"territory": territory,
			"mobile_no": "01099999999",
		})
		local.insert(ignore_permissions=True)
		frappe.db.commit()

		payload = {
			"name": "SYNCTEST-Central Guy",
			"customer_name": "Central Guy",
			"customer_type": "Individual",
			"customer_group": cg,
			"territory": territory,
			"mobile_no": "01099999999",
		}
		result = adapter.apply_incoming(payload, "update")
		assert result == local.name, f"Expected {local.name}, got {result}"

		count = frappe.db.count("Customer", {"mobile_no": "01099999999"})
		assert count == 1, f"Expected 1 customer with this mobile, got {count}"
		print("PASS: test_customer_adapter_dedup_by_mobile")
	finally:
		_cleanup()


def test_customer_adapter_creates_new():
	"""If no mobile_no match, create normally."""
	_cleanup()
	try:
		from pos_next.sync.adapters.customer import CustomerAdapter
		adapter = CustomerAdapter()
		cg, territory = _get_customer_defaults()

		payload = {
			"name": "SYNCTEST-NewCust",
			"customer_name": "SYNCTEST-NewCust",
			"customer_type": "Individual",
			"customer_group": cg,
			"territory": territory,
			"mobile_no": "01055555555",
		}
		result = adapter.apply_incoming(payload, "update")
		assert frappe.db.exists("Customer", result)
		print("PASS: test_customer_adapter_creates_new")
	finally:
		_cleanup()


def run_all():
	test_customer_adapter_registered()
	test_customer_adapter_conflict_key()
	test_customer_adapter_dedup_by_mobile()
	test_customer_adapter_creates_new()
	print("\nAll CustomerAdapter tests PASSED")
