"""Bootstrap test runner for pos_next.

`python -m unittest` imports test modules before `frappe.init`, and `bench run-tests`
dies on ERPNext bootstrap. This inits and connects to the site first, then loads the
modules named on the command line.

	./env/bin/python apps/pos_next/pos_next/_pn_run_tests.py pos_next.api.test_items ...

Run serially: parallel runs deadlock on Stock Settings / tabSingles (error 1213).
"""

import os
import sys
import unittest
from pathlib import Path

# sys.path[0] is this file's own directory, where `import pos_next` resolves to the
# nested pos_next/pos_next module dir and hides `pos_next.pos_next`. Point it at the
# app root so the top-level package wins.
_APP_ROOT = str(Path(__file__).resolve().parent.parent)
if sys.path and sys.path[0] != _APP_ROOT:
	sys.path[0] = _APP_ROOT

import frappe

SITE = "erpnext16.localhost"
SITES_PATH = os.environ.get("SITES_PATH", "sites")


def main(module_names: list[str]) -> int:
	if not module_names:
		print(__doc__)
		return 2

	frappe.init(site=SITE, sites_path=SITES_PATH)
	frappe.connect()
	frappe.flags.in_test = True

	loader = unittest.TestLoader()
	suite = unittest.TestSuite()
	for name in module_names:
		suite.addTests(loader.loadTestsFromName(name))

	result = unittest.TextTestRunner(verbosity=2).run(suite)
	frappe.destroy()
	return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
