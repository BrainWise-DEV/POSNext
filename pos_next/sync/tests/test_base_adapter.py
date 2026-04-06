# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt


def test_base_adapter_interface():
	"""BaseSyncAdapter has the expected methods."""
	from pos_next.sync.adapters.base import BaseSyncAdapter
	required = {"serialize", "apply_incoming", "conflict_key", "validate_incoming", "pre_apply_transform"}
	for method in required:
		assert hasattr(BaseSyncAdapter, method), f"Missing: {method}"
	print("PASS: test_base_adapter_interface")


def test_base_adapter_default_conflict_key():
	"""Default conflict_key returns ('name',)."""
	from pos_next.sync.adapters.base import BaseSyncAdapter

	class DummyAdapter(BaseSyncAdapter):
		doctype = "Item"

	adapter = DummyAdapter()
	assert adapter.conflict_key({"name": "ITEM-001"}) == ("name",)
	print("PASS: test_base_adapter_default_conflict_key")


def test_base_adapter_default_validate_passes():
	"""Default validate_incoming does nothing (no raise)."""
	from pos_next.sync.adapters.base import BaseSyncAdapter

	class DummyAdapter(BaseSyncAdapter):
		doctype = "Item"

	adapter = DummyAdapter()
	adapter.validate_incoming({"name": "ITEM-001"})  # should not raise
	print("PASS: test_base_adapter_default_validate_passes")


def test_base_adapter_default_pre_apply_transform_identity():
	"""Default pre_apply_transform returns payload unchanged."""
	from pos_next.sync.adapters.base import BaseSyncAdapter

	class DummyAdapter(BaseSyncAdapter):
		doctype = "Item"

	adapter = DummyAdapter()
	p = {"name": "ITEM-001", "price": 100}
	result = adapter.pre_apply_transform(p)
	assert result == p
	print("PASS: test_base_adapter_default_pre_apply_transform_identity")


def run_all():
	test_base_adapter_interface()
	test_base_adapter_default_conflict_key()
	test_base_adapter_default_validate_passes()
	test_base_adapter_default_pre_apply_transform_identity()
	print("\nAll BaseSyncAdapter tests PASSED")
