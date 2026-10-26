# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""POS Expense authorization actions.

The void gate is **opt-in**: nothing is enforced until a System Manager creates a
``POS Authorization Rule`` for "Void POS Expense" (globally or per POS Profile). With no
matching rule, ``policy.resolve_rule`` returns ``None``, the gate lets the cancel through
and the POS skips the approval dialog -- the same rule-driven behaviour as the return
actions. Client and server both ask the same question (``get_authorization_policy`` /
``policy.resolve_rule``), so they cannot disagree about whether approval is needed.

The security-relevant context (POS Profile and amount) is never taken from the client:
:func:`resolve_void_context` derives it from the Journal Entry and its opening shift, and
is used both when the grant is minted and when it is spent, so both sides bind to the same
values.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from pos_next.authorization.registry import Action, register

ACTION_VOID_POS_EXPENSE = "Void POS Expense"


def resolve_void_context(journal_entry, client_context=None, pos_profile=None) -> dict:
	"""Authoritative context for voiding ``journal_entry``, derived server-side.

	Validates that the Journal Entry is a submitted POS expense, that its opening shift is
	open and belongs to the current user, and that any client-supplied ``pos_profile``
	matches that shift's profile. ``pos_profile`` and ``amount`` always come from the
	database; the client's values are only checked, never trusted.
	"""
	if not journal_entry:
		frappe.throw(_("Journal Entry is required"))

	je = frappe.db.get_value(
		"Journal Entry",
		journal_entry,
		["name", "docstatus", "posa_is_pos_expense", "posa_pos_opening_shift", "posa_expense_amount"],
		as_dict=True,
	)
	if not je or not cint(je.posa_is_pos_expense) or je.docstatus != 1:
		frappe.throw(_("Journal Entry {0} is not a submitted POS expense").format(journal_entry))

	shift = frappe.db.get_value(
		"POS Opening Shift",
		je.posa_pos_opening_shift,
		["name", "status", "pos_profile", "user", "docstatus"],
		as_dict=True,
	)
	if not shift or shift.docstatus != 1 or shift.status != "Open":
		frappe.throw(_("POS Opening Shift must be open to cancel an expense"))

	if shift.user != frappe.session.user:
		frappe.throw(_("You can only manage expenses for your own open shift"))

	claimed = pos_profile or (client_context or {}).get("pos_profile")
	if claimed and claimed != shift.pos_profile:
		frappe.throw(_("POS Opening Shift does not belong to the selected POS Profile"))

	return {
		"pos_profile": shift.pos_profile,
		"journal_entry": je.name,
		"amount": abs(flt(je.posa_expense_amount)),
	}


# Enforced from cancel_pos_expense via gate.enforce_context; no doctype hook.
register(
	Action(
		name=ACTION_VOID_POS_EXPENSE,
		binding=lambda ctx: {
			"pos_profile": ctx.get("pos_profile"),
			"journal_entry": ctx.get("journal_entry"),
			"amount": abs(flt(ctx.get("amount"))),
		},
	)
)
