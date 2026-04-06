# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt


def test_registry_register_and_lookup():
	from pos_next.sync.adapters.base import BaseSyncAdapter
	from pos_next.sync import registry

	class FakeItemAdapter(BaseSyncAdapter):
		doctype = "Fake Item"

	registry.register(FakeItemAdapter)
	got = registry.get_adapter("Fake Item")
	assert isinstance(got, FakeItemAdapter)
	print("PASS: test_registry_register_and_lookup")


def test_registry_unknown_returns_none():
	from pos_next.sync import registry
	got = registry.get_adapter("Does Not Exist")
	assert got is None
	print("PASS: test_registry_unknown_returns_none")


def test_registry_list_registered():
	from pos_next.sync.adapters.base import BaseSyncAdapter
	from pos_next.sync import registry

	class A(BaseSyncAdapter):
		doctype = "Alpha"

	class B(BaseSyncAdapter):
		doctype = "Beta"

	registry.register(A)
	registry.register(B)
	registered = registry.list_registered()
	assert "Alpha" in registered
	assert "Beta" in registered
	print("PASS: test_registry_list_registered")


def run_all():
	test_registry_register_and_lookup()
	test_registry_unknown_returns_none()
	test_registry_list_registered()
	print("\nAll Registry tests PASSED")
