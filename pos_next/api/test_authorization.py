# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Tests for pos_next.api.authorization — the endpoints themselves, not just the domain
functions underneath them.

request_grant() in particular is worth exercising end-to-end: it's the one place a
stale reference to a since-renamed pin.py constant (LOCKOUT_SECONDS -> lockout_seconds())
slipped through undetected, because every other authorization test calls pin_store /
policy / grants directly rather than through this API layer.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.api.authorization import request_grant, set_authorization_pin
from pos_next.authorization import pin as pin_store
from pos_next.authorization.tests.helpers import (
	DUMMY_ACTION,
	GOOD_PIN,
	MANAGER,
	OTHER_PIN,
	OUTSIDER,
	ROLE,
	make_role,
	make_rule,
	make_user,
)


class TestRequestGrant(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_role(ROLE)
		make_user(MANAGER, [ROLE])
		pin_store.set_pin(MANAGER, GOOD_PIN)

	def setUp(self):
		frappe.set_user("Administrator")
		pin_store.clear_failures(MANAGER)
		make_rule(DUMMY_ACTION, [{"approver_type": "Role", "role": ROLE}])

	def test_wrong_pin_that_triggers_lockout_on_this_attempt_does_not_crash(self):
		"""The exact path the stale LOCKOUT_SECONDS reference broke: a wrong PIN whose
		failure count also crosses max_failures() on this very call.
		"""
		for _ in range(pin_store.max_failures() - 1):
			pin_store.register_failure(MANAGER)

		result = request_grant(DUMMY_ACTION, MANAGER, OTHER_PIN, context={})

		self.assertFalse(result["authorized"])
		self.assertIn("locked", result["message"].lower())

	def test_correct_pin_grants_a_token(self):
		result = request_grant(DUMMY_ACTION, MANAGER, GOOD_PIN, context={})
		self.assertTrue(result["authorized"])
		self.assertTrue(result["grant_token"])


class TestSetAuthorizationPin(FrappeTestCase):
	"""Setting your own PIN is self-service; setting someone else's is an admin action —
	the same authority as clear_authorization_pin, which is System Manager only.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(MANAGER, [])
		make_user(OUTSIDER, [])

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_setting_own_pin_does_not_require_system_manager(self):
		pin_store.set_pin(OUTSIDER, GOOD_PIN)
		frappe.set_user(OUTSIDER)

		result = set_authorization_pin(user=OUTSIDER, new_pin=OTHER_PIN, current_pin=GOOD_PIN)

		self.assertTrue(result["success"])

	def test_setting_anothers_pin_without_system_manager_is_denied(self):
		frappe.set_user(OUTSIDER)
		in_test = frappe.flags.in_test
		frappe.flags.in_test = False
		try:
			with self.assertRaises(frappe.PermissionError):
				set_authorization_pin(user=MANAGER, new_pin=OTHER_PIN)
		finally:
			frappe.flags.in_test = in_test

	def test_system_manager_can_set_anothers_pin(self):
		make_user(OUTSIDER, ["System Manager"])
		frappe.set_user(OUTSIDER)
		in_test = frappe.flags.in_test
		frappe.flags.in_test = False
		try:
			result = set_authorization_pin(user=MANAGER, new_pin=OTHER_PIN)
		finally:
			frappe.flags.in_test = in_test

		self.assertTrue(result["success"])
