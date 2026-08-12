# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""The gate itself — the only place an action is allowed through or refused.

Two entry points, because not every gated action has a document:

* :func:`enforce_document` is a ``doc_events`` hook. It asks the registry which actions
  belong to this doctype, and enforces the ones that fire for this document.
* :func:`enforce_context` is for actions raised from the cart — a discount override, a
  price edit — where no document exists yet.

Both are action-agnostic. Neither knows what a return is.
"""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from pos_next.authorization import grants, log, policy, registry

#: Where the client's grant token rides. A transient ``doc.flags`` entry, never a
#: DocField — nothing to persist, redact or leak, and a submission arriving by any other
#: path simply has no flag and is refused.
TOKEN_FLAG = "pos_auth_token"

FIELD_AUTHORIZED_BY = "custom_authorized_by"
FIELD_AUTHORIZED_AT = "custom_authorized_at"


def enforce_document(doc, method=None):
	"""``doc_events`` entry point. One generic hook line covers every document action."""
	for action in registry.for_doctype(doc.doctype):
		if action.applies and not action.applies(doc):
			continue

		_enforce(
			action,
			context_from_doc(doc),
			doc.flags.get(TOKEN_FLAG),
			reference=doc.name,
			doc=doc,
		)


def enforce_context(action_name: str, context: dict, token: str | None, reference: str | None = None):
	"""Enforce an action that has no document yet. Returns the grant, or ``None``."""
	action = registry.get(action_name)
	if not action:
		frappe.throw(_("Unknown authorization action {0}").format(action_name))

	return _enforce(action, context or {}, token, reference=reference)


def is_required(action_name: str, pos_profile: str | None = None) -> bool:
	"""Whether a rule currently gates ``action_name`` on this profile."""
	return policy.resolve_rule(action_name, pos_profile) is not None


def context_from_doc(doc) -> dict:
	"""Normalised context for a document-triggered action.

	``amount`` is absolute: return invoices carry a negative ``grand_total``, and the
	binding compares magnitudes so the client and the server agree.
	"""

	as_dict = getattr(doc, "as_dict", None)

	return {
		"doc": as_dict() if callable(as_dict) else dict(doc),
		"pos_profile": doc.get("pos_profile"),
		"customer": doc.get("customer"),
		"return_against": doc.get("return_against"),
		"amount": abs(flt(doc.get("grand_total"))),
	}


def _enforce(action, context: dict, token: str | None, reference=None, doc=None):
	rule = policy.resolve_rule(action.name, context.get("pos_profile"))
	if not rule:
		return None

	grant = grants.consume(token, action.name, action.binding(context), reference) if token else None

	if not grant:
		log.record(
			action=action.name,
			result=log.RESULT_DENIED,
			reference=reference,
			pos_profile=context.get("pos_profile"),
			survive_rollback=True,
		)
		approvers = policy.describe_approvers(rule)
		frappe.throw(
			_("{0} requires authorization by: {1}").format(frappe._(action.name), approvers)
			if approvers
			else _("{0} requires authorization.").format(frappe._(action.name)),
			title=_("Authorization Required"),
		)

	if doc is not None:
		doc.set(FIELD_AUTHORIZED_BY, grant["approver"])
		doc.set(FIELD_AUTHORIZED_AT, now_datetime())

	log.record(
		action=action.name,
		approver=grant["approver"],
		result=log.RESULT_GRANTED,
		reference=reference,
		pos_profile=context.get("pos_profile"),
	)

	return grant
