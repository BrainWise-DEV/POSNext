# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""D-R4-07: a cashier of the POS Profile gets its sales persons without a 403.

get_sales_persons read Sales Person with frappe.get_list, which a cashier without
read permission on Sales Person is refused ("No permission for Sales Person"), on every
POS load. The read is scoped to the profile's users, returns only the picker fields,
and returns nothing when the profile's POS Settings do not use sales persons.

Run:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_sales_persons_cashier'}"
"""

import unittest

import frappe

from pos_next.api.pos_profile import get_sales_persons

PREFIX = "_PNXT_I1_"
USER = "_pnxt_i1_sp_cashier@example.com"
OUTSIDER = "_pnxt_i1_sp_outsider@example.com"


class TestSalesPersonsForCashier(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		row = frappe.db.get_value("POS Settings", {"enabled": 1}, ["name", "pos_profile"], as_dict=True)
		if not row or not row.pos_profile:
			self.skipTest("no enabled POS Settings with a POS Profile")
		self.settings, self.profile = row.name, row.pos_profile
		for email in (USER, OUTSIDER):
			if not frappe.db.exists("User", email):
				frappe.get_doc(
					{"doctype": "User", "email": email, "first_name": PREFIX, "send_welcome_email": 0}
				).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "POS Profile User",
				"parent": self.profile,
				"parenttype": "POS Profile",
				"parentfield": "applicable_for_users",
				"user": USER,
			}
		).db_insert()
		root = frappe.db.get_value("Sales Person", {"is_group": 1}, "name")
		self.person = frappe.get_doc(
			{
				"doctype": "Sales Person",
				"sales_person_name": f"{PREFIX}Seller",
				"parent_sales_person": root,
				"is_group": 0,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("POS Settings", self.settings, "enable_sales_persons", "Single")

	def tearDown(self):
		frappe.set_user("Administrator")
		# bench execute commits on return: nothing written here may outlive the test
		frappe.db.rollback()

	def test_cashier_without_sales_person_read_gets_the_list(self):
		frappe.set_user(USER)
		self.assertFalse(frappe.has_permission("Sales Person", "read"))
		names = [row.name for row in get_sales_persons(self.profile)]
		self.assertIn(self.person.name, names)

	def test_only_the_picker_fields(self):
		frappe.set_user(USER)
		row = next(r for r in get_sales_persons(self.profile) if r.name == self.person.name)
		# commission_rate is shown in the picker ("2% comm."); nothing else leaves (review M7)
		self.assertEqual(set(row), {"name", "sales_person_name", "commission_rate"})

	def test_nothing_when_the_profile_does_not_use_sales_persons(self):
		frappe.db.set_value("POS Settings", self.settings, "enable_sales_persons", "Disabled")
		frappe.set_user(USER)
		self.assertEqual(get_sales_persons(self.profile), [])

	def test_a_user_outside_the_profile_is_refused(self):
		frappe.set_user(OUTSIDER)
		with self.assertRaises(frappe.ValidationError):
			get_sales_persons(self.profile)
