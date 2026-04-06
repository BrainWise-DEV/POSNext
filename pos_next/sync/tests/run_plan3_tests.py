# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Run every Plan 3 test module and report PASS/FAIL counts."""

import traceback


TEST_MODULES = [
	"pos_next.sync.tests.test_submittable_adapter",
	"pos_next.sync.tests.test_hooks_outbox",
	"pos_next.sync.tests.test_ingest_api",
	"pos_next.sync.tests.test_outbox_drainer",
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
	print(f"\n\n=== PLAN 3 SUMMARY: {passed} passed, {failed} failed ===")
	if failed:
		raise SystemExit(1)
