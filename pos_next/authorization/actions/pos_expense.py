# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""POS Expense authorization actions."""

from frappe.utils import flt

from pos_next.authorization.registry import Action, register

ACTION_VOID_POS_EXPENSE = "Void POS Expense"

# Enforced from cancel_pos_expense via gate.enforce_context; no doctype hook.
register(
	Action(
		name=ACTION_VOID_POS_EXPENSE,
		binding=lambda ctx: {
			"pos_profile": ctx.get("pos_profile"),
			"journal_entry": ctx.get("journal_entry"),
			"amount": flt(ctx.get("amount")),
		},
	)
)
