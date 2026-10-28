# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Integration test (needs a site): the Sales Person validate hook is wired.

The logic itself is covered site-less in test_pos_sales_team_resolution; this
checks that saving a Sales Person really runs it through hooks.py doc_events
(child-row controllers are never validated by Frappe).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

TABLE = "custom_item_group_commissions"


class TestSalesPersonCommissionHook(FrappeTestCase):
	def setUp(self):
		if not frappe.get_meta("Sales Person").has_field(TABLE):
			self.skipTest("POS Next Sales Person commission fields are not installed")

	def _sales_person(self, rows):
		doc = frappe.new_doc("Sales Person")
		doc.sales_person_name = "_Test POS Next Commission SP"
		doc.is_group = 0
		for row in rows:
			doc.append(TABLE, row)
		return doc

	def test_duplicate_item_group_rejected(self):
		doc = self._sales_person(
			[
				{"item_group": "_Test POS Next IG", "commission_rate": 5},
				{"item_group": "_Test POS Next IG", "commission_rate": 7},
			]
		)
		with self.assertRaises(frappe.ValidationError):
			doc.run_method("validate")

	def test_rate_above_100_rejected(self):
		doc = self._sales_person([{"item_group": "_Test POS Next IG", "commission_rate": 150}])
		with self.assertRaises(frappe.ValidationError):
			doc.run_method("validate")

	def test_valid_rows_pass(self):
		doc = self._sales_person(
			[
				{"item_group": "_Test POS Next IG", "commission_rate": 5},
				{"item_group": "_Test POS Next IG 2", "commission_rate": 100},
			]
		)
		doc.run_method("validate")
