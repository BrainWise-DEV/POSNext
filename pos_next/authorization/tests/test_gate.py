# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Tests for pos_next.authorization.gate.

The important class here: it drives the whole gate through a **dummy action**
registered in tests/helpers.py, touching no return code at all. If the framework has
leaked return-specific assumptions, this fails immediately rather than six months from
now when somebody tries to gate discounts.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.authorization import gate, grants, registry
from pos_next.authorization import pin as pin_store
from pos_next.authorization.tests.helpers import (
	CASHIER,
	DUMMY_ACTION,
	GOOD_PIN,
	MANAGER,
	ROLE,
	make_role,
	make_rule,
	make_user,
)


class TestAuthorizationFramework(FrappeTestCase):
	"""The gate must work for an action it has never heard of before."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_role(ROLE)
		make_user(CASHIER)
		make_user(MANAGER, [ROLE])
		pin_store.set_pin(MANAGER, GOOD_PIN)

	def setUp(self):
		frappe.set_user("Administrator")
		pin_store.clear_failures(MANAGER)

	def test_dummy_action_flows_end_to_end_without_any_return_code(self):
		"""Register an action, gate it, approve it, spend it — no Sales Invoice involved."""
		make_rule(DUMMY_ACTION, [{"approver_type": "Role", "role": ROLE}])

		self.assertTrue(gate.is_required(DUMMY_ACTION))

		context = {"widget": "W-1", "amount": 500}
		action = registry.get(DUMMY_ACTION)
		self.assertIsNotNone(action)

		token = grants.issue(DUMMY_ACTION, MANAGER, action.binding(context))
		result = gate.enforce_context(DUMMY_ACTION, context, token, reference="W-1")

		self.assertIsNotNone(result)
		self.assertEqual(result["approver"], MANAGER)

	def test_unregistered_action_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			gate.enforce_context("_pnxt_not_a_real_action", {}, "irrelevant")

	def test_no_rule_means_no_gate(self):
		"""The live-client safety property: unconfigured actions behave as before."""
		frappe.db.delete("POS Authorization Rule", {"action": DUMMY_ACTION})
		self.assertFalse(gate.is_required(DUMMY_ACTION))
		self.assertIsNone(gate.enforce_context(DUMMY_ACTION, {"widget": "W-1"}, None))

	def test_missing_token_is_denied(self):
		make_rule(DUMMY_ACTION, [{"approver_type": "Role", "role": ROLE}])
		with self.assertRaises(frappe.ValidationError):
			gate.enforce_context(DUMMY_ACTION, {"widget": "W-1", "amount": 10}, None)
