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
