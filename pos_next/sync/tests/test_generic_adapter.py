# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt


def test_generic_adapter_registered_for_all_masters():
	"""GenericMasterAdapter registers for all simple master DocTypes."""
	from pos_next.sync.adapters import generic_master  # triggers registration
	from pos_next.sync import registry

	expected = [
		"POS Profile", "Warehouse", "Mode of Payment", "Item Group",
		"UOM", "Price List", "Company", "Currency", "Branch",
		"Customer Group", "Sales Person", "Employee", "User",
		"Role Profile", "Sales Taxes and Charges Template",
		"Item Tax Template", "POS Settings", "Loyalty Program",
		"Item Barcode",
	]
	registered = registry.list_registered()
	for dt in expected:
		assert dt in registered, f"{dt} not registered by GenericMasterAdapter"
	print("PASS: test_generic_adapter_registered_for_all_masters")


def test_generic_adapter_uses_default_behavior():
	"""GenericMasterAdapter has default conflict_key and validate_incoming."""
	from pos_next.sync.adapters.generic_master import GenericMasterAdapter

	adapter = GenericMasterAdapter()
	adapter.doctype = "Warehouse"
	assert adapter.conflict_key({"name": "WH-001"}) == ("name",)
	adapter.validate_incoming({"name": "WH-001"})  # should not raise
	print("PASS: test_generic_adapter_uses_default_behavior")


def run_all():
	test_generic_adapter_registered_for_all_masters()
	test_generic_adapter_uses_default_behavior()
	print("\nAll GenericMasterAdapter tests PASSED")
