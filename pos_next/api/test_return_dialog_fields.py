# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""D-R4-09 (d, e): what the return dialog shows.

(d) "Process Return" showed an empty status pill: the original invoice it reads had no
status. (e) The Return list showed grand_total (287.52) where the customer paid 288.00:
the list now carries the paid amount, change and rounded total.

Read-only on existing submitted POS invoices.

Run:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_return_dialog_fields'}"
"""

import unittest

import frappe

from pos_next.api import invoices


class TestReturnDialogFields(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.rows = invoices.get_returnable_invoices(limit=5)
		if not self.rows:
			self.skipTest("no returnable POS invoice on this site")

	def test_list_carries_what_was_paid(self):
		for row in self.rows:
			for field in ("paid_amount", "change_amount", "rounded_total", "grand_total"):
				self.assertIn(field, row)

	def test_search_carries_what_was_paid(self):
		name = self.rows[0]["name"]
		found = invoices.search_invoice_by_number(name)
		self.assertTrue(found)
		self.assertIn("paid_amount", found[0])
		self.assertIn("change_amount", found[0])

	def test_original_invoice_has_its_status(self):
		name = self.rows[0]["name"]
		original = invoices.prepare_return_invoice(name)["_original_invoice"]
		self.assertEqual(original.get("status"), frappe.db.get_value("Sales Invoice", name, "status"))
		self.assertIn("change_amount", original)
