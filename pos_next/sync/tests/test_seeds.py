# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


def _cleanup():
	frappe.db.delete("Sync Site Config")
	frappe.db.commit()


def test_seeds_populate_registry():
	"""seed_default_rules returns a list of Sync DocType Rule dicts."""
	from pos_next.sync.seeds import DEFAULT_SYNC_RULES
	assert isinstance(DEFAULT_SYNC_RULES, list)
	assert len(DEFAULT_SYNC_RULES) >= 20, f"Expected at least 20 seeded rules, got {len(DEFAULT_SYNC_RULES)}"
	required_keys = {"doctype_name", "direction", "cdc_strategy", "conflict_rule", "priority"}
	for rule in DEFAULT_SYNC_RULES:
		missing = required_keys - set(rule.keys())
		assert not missing, f"Rule {rule.get('doctype_name')} missing keys: {missing}"
	print("PASS: test_seeds_populate_registry")


def test_seeds_include_required_doctypes():
	"""Seeds include the core DocTypes from the spec."""
	from pos_next.sync.seeds import DEFAULT_SYNC_RULES
	names = {r["doctype_name"] for r in DEFAULT_SYNC_RULES}
	required = {
		"Item", "Item Price", "POS Profile", "Warehouse", "Customer",
		"Sales Invoice", "Payment Entry", "POS Opening Shift",
		"POS Closing Shift", "Stock Ledger Entry", "User", "Mode of Payment",
	}
	missing = required - names
	assert not missing, f"Missing from seeds: {missing}"
	print("PASS: test_seeds_include_required_doctypes")


def test_apply_seeds_to_config():
	"""apply_seeds_to_config populates synced_doctypes on a config row."""
	_cleanup()
	try:
		from pos_next.sync.seeds import apply_seeds_to_config
		doc = frappe.get_doc({
			"doctype": "Sync Site Config",
			"site_role": "Central",
			"branch_code": "HQ",
			"enabled": 1,
		})
		doc.insert(ignore_permissions=True)
		apply_seeds_to_config(doc)
		doc.reload()
		assert len(doc.synced_doctypes) >= 20, f"Expected >=20 rules, got {len(doc.synced_doctypes)}"
		print("PASS: test_apply_seeds_to_config")
	finally:
		_cleanup()


def test_priorities_are_sorted_correctly():
	"""POS Opening Shift has lowest priority (synced first)."""
	from pos_next.sync.seeds import DEFAULT_SYNC_RULES
	by_name = {r["doctype_name"]: r for r in DEFAULT_SYNC_RULES}
	opening_prio = by_name["POS Opening Shift"]["priority"]
	invoice_prio = by_name["Sales Invoice"]["priority"]
	assert opening_prio < invoice_prio, (
		f"POS Opening Shift priority ({opening_prio}) should be < "
		f"Sales Invoice priority ({invoice_prio})"
	)
	print("PASS: test_priorities_are_sorted_correctly")


def run_all():
	test_seeds_populate_registry()
	test_seeds_include_required_doctypes()
	test_apply_seeds_to_config()
	test_priorities_are_sorted_correctly()
	print("\nAll Seeds tests PASSED")
