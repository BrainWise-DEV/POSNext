# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Run every Plan 2 test module and report PASS/FAIL counts."""

import traceback


TEST_MODULES = [
	"pos_next.sync.tests.test_changes_api",
	"pos_next.sync.tests.test_generic_adapter",
	"pos_next.sync.tests.test_item_adapter",
	"pos_next.sync.tests.test_item_price_adapter",
	"pos_next.sync.tests.test_customer_adapter",
	"pos_next.sync.tests.test_masters_puller",
]


def run():
	passed = 0
	failed = 0
	for mod_name in TEST_MODULES:
		print(f"\n=== {mod_name} ===")
		try:
			mod = __import__(mod_name, fromlist=["run_all"])
			mod.run_all()
			passed += 1
		except Exception:
			failed += 1
			print(f"FAILED: {mod_name}")
			traceback.print_exc()
	print(f"\n\n=== PLAN 2 SUMMARY: {passed} passed, {failed} failed ===")
	if failed:
		raise SystemExit(1)
