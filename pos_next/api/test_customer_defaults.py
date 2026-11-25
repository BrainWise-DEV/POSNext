# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import unittest

import frappe

from pos_next.api.customers import get_customer_defaults


class TestCustomerDefaults(unittest.TestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_returns_the_two_defaults_and_the_leaf_groups(self):
		result = get_customer_defaults()
		self.assertEqual(set(result), {"customer_group", "territory", "customer_groups"})
		self.assertEqual(
			result["customer_group"], frappe.db.get_single_value("Selling Settings", "customer_group")
		)
		self.assertEqual(result["territory"], frappe.db.get_single_value("Selling Settings", "territory"))
		leaves = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name")
		self.assertTrue(leaves)
		self.assertCountEqual(result["customer_groups"], leaves)

	def test_needs_permission_to_create_a_customer(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_customer_defaults()

	def test_is_whitelisted_and_not_guest_callable(self):
		self.assertIn(get_customer_defaults, frappe.whitelisted)
		self.assertNotIn(get_customer_defaults, frappe.guest_methods)
