#!/usr/bin/env python3
"""Run POS Next split smoke tests outside bench test runner."""

import os
import sys
import unittest

import frappe

BENCH_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(BENCH_PATH, "apps"))


def bootstrap(site: str):
	os.chdir(os.path.join(BENCH_PATH, "sites"))
	frappe.init(site=site)
	frappe.connect()
	frappe.set_user("Administrator")


def main():
	bootstrap("brainwise.dev")
	from pos_next.test_no_promotions_import import TestNoPromotionsImport
	from pos_next.test_split_smoke import TestMagentoSplitSmoke

	loader = unittest.defaultTestLoader
	suite = unittest.TestSuite()
	for cls in (TestNoPromotionsImport, TestMagentoSplitSmoke):
		suite.addTests(loader.loadTestsFromTestCase(cls))
	result = unittest.TextTestRunner(verbosity=2).run(suite)
	frappe.destroy()
	return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
	sys.exit(main())
