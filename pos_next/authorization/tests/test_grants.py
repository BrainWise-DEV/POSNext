# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Tests for pos_next.authorization.grants — binding and consumption rules, pure logic,
no documents.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.authorization import grants
from pos_next.authorization.tests.helpers import CASHIER, DUMMY_ACTION, MANAGER


class TestGrants(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_grant_is_single_purpose_across_references(self):
		token = grants.issue(DUMMY_ACTION, MANAGER, {"widget": "W-1"})
		self.assertIsNotNone(grants.consume(token, DUMMY_ACTION, {"widget": "W-1"}, "DOC-A"))
		# Same token, different document — refused.
		self.assertIsNone(grants.consume(token, DUMMY_ACTION, {"widget": "W-1"}, "DOC-B"))

	def test_grant_survives_retry_of_the_same_document(self):
		"""Redis is not transactional with MariaDB; an on_submit failure must not burn it."""
		token = grants.issue(DUMMY_ACTION, MANAGER, {"widget": "W-1"})
		self.assertIsNotNone(grants.consume(token, DUMMY_ACTION, {"widget": "W-1"}, "DOC-A"))
		self.assertIsNotNone(grants.consume(token, DUMMY_ACTION, {"widget": "W-1"}, "DOC-A"))

	def test_grant_is_bound_to_its_action(self):
		token = grants.issue(DUMMY_ACTION, MANAGER, {"widget": "W-1"})
		self.assertIsNone(grants.consume(token, "some_other_action", {"widget": "W-1"}, "DOC-A"))

	def test_unknown_token_is_refused(self):
		self.assertIsNone(grants.consume("not-a-token", DUMMY_ACTION, {}, "DOC-A"))

	def test_amount_binding_is_one_directional(self):
		approved = {"return_against": "SINV-1", "amount": 100000}
		self.assertTrue(grants.binding_matches(approved, {"return_against": "SINV-1", "amount": 80000}))
		self.assertTrue(grants.binding_matches(approved, {"return_against": "SINV-1", "amount": 100000}))
		self.assertFalse(grants.binding_matches(approved, {"return_against": "SINV-1", "amount": 120000}))

	def test_non_amount_keys_must_match_exactly(self):
		approved = {"return_against": "SINV-1", "amount": 100}
		self.assertFalse(grants.binding_matches(approved, {"return_against": "SINV-2", "amount": 100}))

	def test_blank_and_missing_are_the_same_absence(self):
		approved = {"return_against": None, "customer": "CUST-1"}
		self.assertTrue(grants.binding_matches(approved, {"return_against": "", "customer": "CUST-1"}))

	def test_grant_is_bound_to_the_requesting_session(self):
		token = grants.issue(DUMMY_ACTION, MANAGER, {"widget": "W-1"})
		frappe.set_user(CASHIER)
		try:
			self.assertIsNone(grants.consume(token, DUMMY_ACTION, {"widget": "W-1"}, "DOC-A"))
		finally:
			frappe.set_user("Administrator")
