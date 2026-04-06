# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt


def test_submittable_adapter_interface():
	"""SubmittableAdapter has apply_incoming that handles docstatus."""
	from pos_next.sync.adapters.submittable import SubmittableAdapter
	assert hasattr(SubmittableAdapter, "apply_incoming")
	assert hasattr(SubmittableAdapter, "doctype")
	print("PASS: test_submittable_adapter_interface")


def test_submittable_adapter_is_base_adapter():
	"""SubmittableAdapter inherits from BaseSyncAdapter."""
	from pos_next.sync.adapters.submittable import SubmittableAdapter
	from pos_next.sync.adapters.base import BaseSyncAdapter
	assert issubclass(SubmittableAdapter, BaseSyncAdapter)
	print("PASS: test_submittable_adapter_is_base_adapter")


def run_all():
	test_submittable_adapter_interface()
	test_submittable_adapter_is_base_adapter()
	print("\nAll SubmittableAdapter tests PASSED")
