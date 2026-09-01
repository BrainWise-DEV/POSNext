#!/usr/bin/env python
"""Bootstrap runner for pos_next tests.

`python -m unittest` imports test modules before `frappe.init`, which crashes,
and `bench run-tests` dies on ERPNext bootstrap (DuplicateEntryError on
'Standard Buying'). This inits frappe first, then loads the named modules.

Usage (inside the container, serial only -- parallel runs deadlock on
Stock Settings/tabSingles with error 1213):

    ./env/bin/python apps/pos_next/pos_next/_pn_run_tests.py pos_next.api.test_packages ...
"""

import os
import sys
import unittest

import frappe

SITE = "erpnext16.localhost"
# frappe.init resolves sites/ relative to the cwd, so anchor at the bench root
# (three levels up from apps/pos_next/pos_next/).
BENCH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SITES_PATH = os.environ.get("SITES_PATH") or os.path.join(BENCH_ROOT, "sites")


def main(module_names):
	if not module_names:
		print(__doc__, file=sys.stderr)
		return 2

	os.chdir(BENCH_ROOT)

	# This script lives in pos_next/, which contains a nested pos_next/ module
	# folder -- leaving the script dir on sys.path makes `pos_next` resolve there
	# (no .api subpackage). Drop it and use the app root instead.
	script_dir = os.path.dirname(os.path.abspath(__file__))
	sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != script_dir]
	if APP_ROOT not in sys.path:
		sys.path.insert(0, APP_ROOT)

	frappe.init(site=SITE, sites_path=SITES_PATH)
	frappe.connect()
	frappe.flags.in_test = True

	try:
		loader = unittest.TestLoader()
		suite = unittest.TestSuite()
		for name in module_names:
			# loadTestsFromName on a package silently collects 0 tests, so
			# modules must always be listed explicitly.
			suite.addTests(loader.loadTestsFromName(name))

		result = unittest.TextTestRunner(verbosity=2).run(suite)
		return 0 if result.wasSuccessful() else 1
	finally:
		frappe.destroy()


if __name__ == "__main__":
	raise SystemExit(main(sys.argv[1:]))
