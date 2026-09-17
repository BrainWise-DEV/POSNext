# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Sales Invoice authorization actions.

The only module in the authorization package that knows what a return is. Everything
else — gate, grants, policy, PIN, log, dialog — is generic.

Two actions rather than one, because the two paths carry different risk. A refund with
no source invoice is the most abusable path in the system and most sites will want it
gated more tightly than an ordinary return, so it gets its own rule.

Note the relationship with ``allow_return_without_invoice`` in POS Settings: that setting
still decides whether the path exists at all. A rule here is a *second* gate on top of
it and can never re-open something the setting has closed.
"""

from frappe.utils import flt

from pos_next.authorization.registry import Action, register

ACTION_SALES_INVOICE_RETURN = "Sales Invoice Return"
ACTION_RETURN_WITHOUT_INVOICE = "Sales Return Without Invoice"

SALES_INVOICE = "Sales Invoice"


def _is_return_against_invoice(doc) -> bool:
	return bool(doc.get("is_return")) and bool(doc.get("return_against"))


def _is_return_without_invoice(doc) -> bool:
	return bool(doc.get("is_return")) and not doc.get("return_against")


register(
	Action(
		name=ACTION_SALES_INVOICE_RETURN,
		doctype=SALES_INVOICE,
		applies=_is_return_against_invoice,
		binding=lambda ctx: {
			"pos_profile": ctx.get("pos_profile"),
			"return_against": ctx.get("return_against"),
			"amount": flt(ctx.get("amount")),
		},
	)
)

register(
	Action(
		name=ACTION_RETURN_WITHOUT_INVOICE,
		doctype=SALES_INVOICE,
		applies=_is_return_without_invoice,
		binding=lambda ctx: {
			"pos_profile": ctx.get("pos_profile"),
			"customer": ctx.get("customer"),
			"amount": flt(ctx.get("amount")),
		},
	)
)
