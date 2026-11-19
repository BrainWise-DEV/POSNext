# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Tests for pos_next.authorization.policy — rule resolution and approver eligibility."""

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.authorization import policy
from pos_next.authorization.tests.helpers import (
	CASHIER,
	DUMMY_ACTION,
	MANAGER,
	OUTSIDER,
	ROLE,
	make_role,
	make_rule,
	make_user,
)


class TestApproverResolution(FrappeTestCase):
	"""Role rows, User rows, OR-ing, conditions and self-approval."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_role(ROLE)
		make_user(CASHIER)
		make_user(MANAGER, [ROLE])
		make_user(OUTSIDER)

	def setUp(self):
		frappe.set_user("Administrator")

	def test_role_row_admits_any_holder(self):
		rule = make_rule(DUMMY_ACTION, [{"approver_type": "Role", "role": ROLE}])
		approvers = policy.eligible_approvers(rule, {})
		self.assertIn(MANAGER, approvers)
		self.assertNotIn(OUTSIDER, approvers)

	def test_user_row_admits_only_that_user(self):
		rule = make_rule(DUMMY_ACTION, [{"approver_type": "User", "user": OUTSIDER}])
		approvers = policy.eligible_approvers(rule, {})
		self.assertEqual(approvers, {OUTSIDER})

	def test_rows_are_or_ed(self):
		rule = make_rule(
			DUMMY_ACTION,
			[
				{"approver_type": "Role", "role": ROLE},
				{"approver_type": "User", "user": OUTSIDER},
			],
		)
		approvers = policy.eligible_approvers(rule, {})
		self.assertIn(MANAGER, approvers)
		self.assertIn(OUTSIDER, approvers)

	def test_false_condition_contributes_nobody(self):
		rule = make_rule(
			DUMMY_ACTION,
			[{"approver_type": "Role", "role": ROLE, "condition": "amount > 50000"}],
		)
		self.assertEqual(policy.eligible_approvers(rule, {"amount": 100}), set())
		self.assertIn(MANAGER, policy.eligible_approvers(rule, {"amount": 60000}))

	def test_invalid_condition_is_rejected_at_save_not_at_the_till(self):
		with self.assertRaises(frappe.ValidationError):
			make_rule(
				DUMMY_ACTION,
				[{"approver_type": "Role", "role": ROLE, "condition": "this is not python ("}],
			)

	def test_runtime_condition_error_is_contained(self):
		"""A condition that blows up must return False, not propagate.

		Save-time validation catches almost everything (see the test above), so this is
		the defensive path: whatever slips through must skip its row rather than make
		every approval in the store impossible.
		"""
		self.assertFalse(policy.eval_condition("doc.missing.attribute > 1", {"amount": 1}))
		self.assertFalse(policy.eval_condition("1 / 0", {"amount": 1}))

		with self.assertRaises(Exception):
			policy.eval_condition("doc.missing.attribute > 1", {"amount": 1}, throw=True)

	def test_self_approval_is_allowed_by_default(self):
		rule = make_rule(DUMMY_ACTION, [{"approver_type": "User", "user": MANAGER}])
		frappe.set_user(MANAGER)
		try:
			self.assertTrue(policy.is_approver(rule, MANAGER, {}))
		finally:
			frappe.set_user("Administrator")

	def test_self_approval_can_be_switched_off_per_rule(self):
		rule = make_rule(
			DUMMY_ACTION,
			[{"approver_type": "User", "user": MANAGER}],
			allow_self_approval=0,
		)
		frappe.set_user(MANAGER)
		try:
			self.assertFalse(policy.is_approver(rule, MANAGER, {}))
		finally:
			frappe.set_user("Administrator")

	def test_rule_without_approvers_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_rule(DUMMY_ACTION, [])

	def test_unregistered_action_cannot_be_saved(self):
		with self.assertRaises(frappe.ValidationError):
			make_rule("_pnxt_never_registered", [{"approver_type": "Role", "role": ROLE}])


class TestRuleResolution(FrappeTestCase):
	"""Profile scoping."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_role(ROLE)
		make_user(MANAGER, [ROLE])

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("POS Authorization Rule", {"action": DUMMY_ACTION})

	def test_no_rule_returns_none(self):
		self.assertIsNone(policy.resolve_rule(DUMMY_ACTION, None))

	def test_catch_all_rule_applies_to_every_profile(self):
		make_rule(DUMMY_ACTION, [{"approver_type": "Role", "role": ROLE}])
		self.assertIsNotNone(policy.resolve_rule(DUMMY_ACTION, "ANY-PROFILE"))

	def test_disabled_rule_does_not_gate(self):
		rule = make_rule(DUMMY_ACTION, [{"approver_type": "Role", "role": ROLE}])
		rule.enabled = 0
		rule.save(ignore_permissions=True)
		self.assertIsNone(policy.resolve_rule(DUMMY_ACTION, None))


class TestRuleUniqueness(FrappeTestCase):
	"""Two enabled rules must never compete for the same (action, POS Profile) —
	resolve_rule() above would otherwise pick between them by whichever was modified
	most recently, silently, with the "losing" rule still showing Enabled in the desk.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_role(ROLE)

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("POS Authorization Rule", {"action": DUMMY_ACTION})

	def _rule(self, pos_profile=None, enabled=1):
		# ignore_links=True: these are fixture profile names, not real POS Profile
		# records — irrelevant to the uniqueness check itself, which only compares the
		# stored string.
		doc = frappe.get_doc(
			{
				"doctype": "POS Authorization Rule",
				"action": DUMMY_ACTION,
				"enabled": enabled,
				"pos_profile": pos_profile,
				"approvers": [{"approver_type": "Role", "role": ROLE}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_links=True)
		return doc

	def test_two_enabled_rules_for_the_same_specific_profile_is_rejected(self):
		self._rule(pos_profile="_PNXT_BRANCH_A")
		with self.assertRaises(frappe.ValidationError):
			self._rule(pos_profile="_PNXT_BRANCH_A")

	def test_two_enabled_catch_all_rules_is_rejected(self):
		self._rule(pos_profile=None)
		with self.assertRaises(frappe.ValidationError):
			self._rule(pos_profile=None)

	def test_enabled_rules_for_different_profiles_are_both_allowed(self):
		self._rule(pos_profile="_PNXT_BRANCH_A")
		self._rule(pos_profile="_PNXT_BRANCH_B")  # must not raise

	def test_a_disabled_rule_does_not_block_a_new_enabled_one(self):
		self._rule(pos_profile="_PNXT_BRANCH_A", enabled=0)
		self._rule(pos_profile="_PNXT_BRANCH_A")  # must not raise

	def test_resaving_the_same_rule_does_not_self_conflict(self):
		rule = self._rule(pos_profile="_PNXT_BRANCH_A")
		rule.allow_self_approval = 0
		rule.save(ignore_permissions=True)  # must not raise
