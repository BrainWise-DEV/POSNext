# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Verify POSNext Cashier fixture permissions in custom_docperm.json."""

import json
import unittest
from pathlib import Path

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "custom_docperm.json"
CASHIER_ROLE = "POSNext Cashier"


class TestCashierPermissionsFixture(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.rows = json.loads(FIXTURE_PATH.read_text())

	def _cashier_row(self, doctype: str) -> dict:
		matches = [
			row
			for row in self.rows
			if row.get("role") == CASHIER_ROLE
			and row.get("parent") == doctype
			and int(row.get("permlevel") or 0) == 0
		]
		self.assertEqual(len(matches), 1, f"Expected exactly 1 {CASHIER_ROLE} row for {doctype}")
		return matches[0]

	def test_unique_fixture_names(self):
		names = [row["name"] for row in self.rows]
		self.assertEqual(len(names), len(set(names)), "Duplicate Custom DocPerm names in fixture")

	def test_cashier_read_only_masters_and_settings(self):
		for doctype in ("Selling Settings", "Customer Group", "POS Governorate", "Sales Person"):
			with self.subTest(doctype=doctype):
				row = self._cashier_row(doctype)
				self.assertEqual(row.get("read"), 1)
				self.assertEqual(row.get("select"), 1)
				self.assertEqual(row.get("write"), 0)
				self.assertEqual(row.get("create"), 0)
				self.assertEqual(row.get("delete"), 0)

	def test_cashier_promotional_scheme_read_write_create(self):
		row = self._cashier_row("Promotional Scheme")
		self.assertEqual(row.get("read"), 1)
		self.assertEqual(row.get("write"), 1)
		self.assertEqual(row.get("create"), 1)
		self.assertEqual(row.get("select"), 1)
		self.assertEqual(row.get("delete"), 0)
