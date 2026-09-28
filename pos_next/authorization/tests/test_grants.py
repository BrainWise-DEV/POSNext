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


class TestGrantValidity(FrappeTestCase):
	"""How long a grant lives, and what a longer life does not buy an attacker."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.settings = frappe.get_single(grants.SETTINGS_DOCTYPE)
		self._original = self.settings.get("grant_ttl_minutes")

	def tearDown(self):
		self._set_ttl_minutes(self._original)

	def _set_ttl_minutes(self, minutes):
		self.settings.db_set("grant_ttl_minutes", minutes, update_modified=False)
		frappe.clear_document_cache(grants.SETTINGS_DOCTYPE, grants.SETTINGS_DOCTYPE)

	def test_validity_comes_from_settings(self):
		self._set_ttl_minutes(7)
		self.assertEqual(grants.ttl_seconds(), 7 * 60)

	def test_unset_or_zero_falls_back_to_the_default(self):
		for value in (0, None):
			self._set_ttl_minutes(value)
			self.assertEqual(grants.ttl_seconds(), grants.GRANT_TTL)

	def test_default_is_long_enough_for_an_offline_sale_to_sync(self):
		"""180s used to expire mid-sale and send the manager back to the till."""
		self.assertGreaterEqual(grants.GRANT_TTL, 10 * 60)

	def test_the_token_actually_carries_the_configured_expiry(self):
		self._set_ttl_minutes(9)
		token = grants.issue(DUMMY_ACTION, MANAGER, {"widget": "W-1"})
		ttl = frappe.cache().ttl(grants._key(token))
		self.assertGreater(ttl, 9 * 60 - 30)
		self.assertLessEqual(ttl, 9 * 60)

	def test_a_retry_refreshes_the_window_rather_than_running_it_down(self):
		"""A slow sale that keeps retrying the same document must not expire mid-retry."""
		self._set_ttl_minutes(9)
		token = grants.issue(DUMMY_ACTION, MANAGER, {"widget": "W-1"})
		key = grants._key(token)

		frappe.cache().expire(key, 5)  # simulate a grant near the end of its life
		self.assertLessEqual(frappe.cache().ttl(key), 5)

		self.assertIsNotNone(grants.consume(token, DUMMY_ACTION, {"widget": "W-1"}, "DOC-A"))
		self.assertGreater(frappe.cache().ttl(key), 5)

	# -- a longer window must not widen what a token can do --------------------

	def test_longer_validity_does_not_let_a_token_move_to_another_document(self):
		self._set_ttl_minutes(60)
		token = grants.issue(DUMMY_ACTION, MANAGER, {"widget": "W-1"})
		self.assertIsNotNone(grants.consume(token, DUMMY_ACTION, {"widget": "W-1"}, "DOC-A"))
		self.assertIsNone(grants.consume(token, DUMMY_ACTION, {"widget": "W-1"}, "DOC-B"))

	def test_longer_validity_does_not_let_another_session_replay_it(self):
		self._set_ttl_minutes(60)
		token = grants.issue(DUMMY_ACTION, MANAGER, {"widget": "W-1"})
		frappe.set_user(CASHIER)
		try:
			self.assertIsNone(grants.consume(token, DUMMY_ACTION, {"widget": "W-1"}, "DOC-A"))
		finally:
			frappe.set_user("Administrator")

	def test_longer_validity_does_not_relax_the_binding(self):
		self._set_ttl_minutes(60)
		token = grants.issue(DUMMY_ACTION, MANAGER, {"widget": "W-1", "amount": 50})
		self.assertIsNone(
			grants.consume(token, DUMMY_ACTION, {"widget": "W-1", "amount": 5000}, "DOC-A")
		)

	def test_revoked_token_stays_dead_regardless_of_validity(self):
		self._set_ttl_minutes(60)
		token = grants.issue(DUMMY_ACTION, MANAGER, {"widget": "W-1"})
		grants.revoke(token)
		self.assertIsNone(grants.consume(token, DUMMY_ACTION, {"widget": "W-1"}, "DOC-A"))
