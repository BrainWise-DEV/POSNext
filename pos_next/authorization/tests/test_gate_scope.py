# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Which submissions ``enforce_document`` is willing to refuse.

The gate can only ever be *satisfied* on a path that attaches a grant token, and the
only path that does is ``pos_next.api.invoices.submit_invoice``. Anything else — a
desk credit note, a patch, a data import — would be refused with no way to approve.

So the gate limits itself to POS documents and to real user submissions. These tests
pin both edges: it must still refuse an unauthorized POS submission (the whole point),
and it must not touch anything else.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.authorization import gate, grants
from pos_next.authorization import pin as pin_store
from pos_next.authorization.tests.helpers import (
	CASHIER,
	GOOD_PIN,
	MANAGER,
	ROLE,
	make_role,
	make_rule,
	make_user,
)

ACTION = "Sales Invoice Return"


class _StubDoc(frappe._dict):
	"""Enough of a Document for the gate: ``get``, ``set`` and ``flags``.

	A real Document is not used here because the gate must be provable without a
	Sales Invoice — the whole framework is meant to be doctype-agnostic.
	"""

	def set(self, field, value):
		self[field] = value


def _return_doc(**overrides):
	"""A minimal stand-in for a return invoice at before_submit."""
	doc = _StubDoc(
		{
			"doctype": "Sales Invoice",
			"name": "_PNXT_AUTH_SI_1",
			"is_return": 1,
			"return_against": "_PNXT_AUTH_SI_0",
			"is_pos": 1,
			"pos_profile": None,
			"customer": "_PNXT_AUTH_CUSTOMER",
			"grand_total": -50.0,
			"flags": frappe._dict(),
		}
	)
	doc.update(overrides)
	return doc


class TestGateScope(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_role(ROLE)
		make_user(CASHIER)
		make_user(MANAGER, [ROLE])
		pin_store.set_pin(MANAGER, GOOD_PIN)
		# A catch-all rule (blank pos_profile) is the widest a rule can be, so it is
		# the case where over-reach would hurt most.
		make_rule(ACTION, [{"approver_type": "Role", "role": ROLE}])

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.flags.pop("in_import", None)

	# -- still refuses what it is for ------------------------------------------

	def test_pos_return_without_a_grant_is_still_refused(self):
		with self.assertRaises(frappe.ValidationError):
			gate.enforce_document(_return_doc())

	def test_pos_return_with_a_valid_grant_is_allowed(self):
		doc = _return_doc()
		context = gate.context_from_doc(doc)
		from pos_next.authorization import registry

		token = grants.issue(ACTION, MANAGER, registry.get(ACTION).binding(context))
		doc.flags[gate.TOKEN_FLAG] = token

		gate.enforce_document(doc)
		self.assertEqual(doc.get(gate.FIELD_AUTHORIZED_BY), MANAGER)

	# -- and leaves everything else alone --------------------------------------

	def test_non_pos_return_is_not_gated(self):
		"""A back-office credit note has no till, no dialog and no way to be approved."""
		gate.enforce_document(_return_doc(is_pos=0, pos_profile=None))

	def test_a_pos_profile_alone_still_counts_as_a_pos_document(self):
		"""Belt and braces: is_pos may be unset on a draft that still belongs to a till."""
		with self.assertRaises(frappe.ValidationError):
			gate.enforce_document(_return_doc(is_pos=0, pos_profile="_PNXT_AUTH_PROFILE"))

	def test_internal_contexts_are_not_gated(self):
		for flag in gate.INTERNAL_FLAGS:
			frappe.flags[flag] = True
			try:
				gate.enforce_document(_return_doc())
			finally:
				frappe.flags.pop(flag, None)

	def test_non_return_pos_invoice_is_not_gated(self):
		"""No registered action applies, so an ordinary sale submits untouched."""
		gate.enforce_document(_return_doc(is_return=0, return_against=None))
