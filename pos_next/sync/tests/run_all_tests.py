# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Run every Plan 1 test module and report PASS/FAIL counts."""

import traceback


TEST_MODULES = [
	"pos_next.sync.tests.test_sync_site_config",
	"pos_next.sync.tests.test_outbox",
	"pos_next.sync.tests.test_watermark",
	"pos_next.sync.tests.test_payload",
	"pos_next.sync.tests.test_base_adapter",
	"pos_next.sync.tests.test_registry",
	"pos_next.sync.tests.test_conflict",
	"pos_next.sync.tests.test_auth",
	"pos_next.sync.tests.test_custom_fields",
	"pos_next.sync.tests.test_backfill",
	"pos_next.sync.tests.test_seeds",
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
	print(f"\n\n=== SUMMARY: {passed} passed, {failed} failed ===")
	if failed:
		raise SystemExit(1)
