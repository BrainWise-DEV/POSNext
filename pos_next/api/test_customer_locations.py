# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""D-R4-10: the customer dialog's Governorate / District lists load for a cashier.

They were read with frappe.client.get_list, which a cashier (no read on POS Governorate
or POS District, System Manager only) is refused with 403. Like D-1's country list, the
dialog now reads them through whitelisted methods gated by the permission to create or
edit a customer.

Run:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_customer_locations'}"
"""

import unittest

import frappe

from pos_next.api import customers

PREFIX = "_PNXT_I1_"
USER = "_pnxt_i1_cashier@example.com"


class TestCustomerLocations(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if not frappe.db.exists("User", USER):
			user = frappe.get_doc(
				{"doctype": "User", "email": USER, "first_name": f"{PREFIX}Cashier", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
			user.add_roles("Sales User")
		self.gov = frappe.get_doc({"doctype": "POS Governorate", "governorate": f"{PREFIX}Giza"}).insert(
			ignore_permissions=True
		)
		self.district = frappe.get_doc(
			{"doctype": "POS District", "governorate": self.gov.name, "district": f"{PREFIX}Dokki"}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		# bench execute commits on return: nothing written here may outlive the test
		frappe.db.rollback()

	def test_cashier_cannot_list_them_directly(self):
		frappe.set_user(USER)
		self.assertFalse(frappe.has_permission("POS Governorate", "read"))

	def test_cashier_reads_governorates(self):
		frappe.set_user(USER)
		self.assertIn(self.gov.name, customers.get_governorates())

	def test_cashier_reads_the_districts_of_a_governorate(self):
		frappe.set_user(USER)
		rows = customers.get_districts(self.gov.name)
		self.assertEqual([(r.name, r.district) for r in rows], [(self.district.name, f"{PREFIX}Dokki")])
		self.assertEqual(customers.get_districts(None), [])

	def test_needs_permission_to_create_or_edit_a_customer(self):
		frappe.set_user("Guest")
		for method in (customers.get_governorates, lambda: customers.get_districts(self.gov.name)):
			with self.assertRaises(frappe.PermissionError):
				method()

	def test_whitelisted_and_not_guest_callable(self):
		for method in (customers.get_governorates, customers.get_districts):
			self.assertIn(method, frappe.whitelisted)
			self.assertNotIn(method, frappe.guest_methods)
