# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Whitelisted endpoints for the POS authorization gate.

None of these decide anything. The authority is
:func:`pos_next.authorization.gate.enforce_document`, which runs on ``before_submit`` and
refuses an action whose grant is missing, expired or bound to something else. These
endpoints exist so the POS can ask *whether* approval is needed, *who* can give it, and
*mint a grant* once someone has proved their PIN.
"""

import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import flt

from pos_next.authorization import gate, grants, log, policy, registry
from pos_next.authorization import pin as pin_store


def _parse_context(context) -> dict:
	"""Normalise the context a client sends alongside an authorization request."""
	if isinstance(context, str):
		context = json.loads(context) if context else {}

	context = dict(context or {})

	context["amount"] = abs(flt(context.get("amount")))
	return context


@frappe.whitelist()
def get_authorization_policy(pos_profile: str | None = None) -> dict:
	policy_map = {}
	for action in registry.all_actions():
		if gate.is_required(action.name, pos_profile):
			policy_map[action.name] = True

	return policy_map


@frappe.whitelist()
def get_authorizers(action: str, pos_profile: str | None = None, context=None) -> list[dict]:
	action_def = registry.get(action)
	if not action_def:
		return []

	context = _parse_context(context)
	context.setdefault("pos_profile", pos_profile)

	rule = policy.resolve_rule(action, context.get("pos_profile"))
	if not rule:
		return []

	candidates = policy.eligible_approvers(rule, context)

	if not rule.get("allow_self_approval"):
		candidates.discard(frappe.session.user)

	with_pin = pin_store.users_with_pin(candidates)
	if not with_pin:
		return []

	rows = frappe.get_all(
		"User",
		filters={"name": ("in", list(with_pin))},
		fields=["name as user", "full_name"],
		order_by="full_name asc",
	)
	return rows


@frappe.whitelist()
def get_authorization_readiness(action: str, pos_profile: str | None = None) -> dict:
	frappe.only_for("System Manager")

	rule = policy.resolve_rule(action, pos_profile)
	if not rule:
		return {"rule": None, "ready": [], "missing_pin": []}

	candidates = policy.eligible_approvers(rule, {"pos_profile": pos_profile})
	with_pin = pin_store.users_with_pin(candidates)

	return {
		"rule": rule.name,
		"ready": sorted(with_pin),
		"missing_pin": sorted(candidates - with_pin),
	}


@frappe.whitelist()
@rate_limit(limit=5, seconds=60)
def request_grant(action: str, approver: str, pin: str, context=None) -> dict:
	action_def = registry.get(action)
	if not action_def:
		return {"authorized": False, "message": _("Unknown authorization action")}

	context = _parse_context(context)
	pos_profile = context.get("pos_profile")

	rule = policy.resolve_rule(action, pos_profile)
	if not rule:
		return {"authorized": False, "message": _("No authorization rule applies to this action.")}

	def _deny(result: str, message: str) -> dict:
		log.record(
			action=action,
			approver=approver,
			result=result,
			pos_profile=pos_profile,
			reference=context.get("return_against"),
		)
		return {"authorized": False, "message": message}

	if pin_store.is_locked_out(approver):
		return _deny(
			log.RESULT_LOCKED_OUT,
			_("Too many failed attempts. Approval is locked for {0} minutes.").format(
				pin_store.lockout_seconds() // 60
			),
		)

	if not policy.is_approver(rule, approver, context):
		return _deny(
			log.RESULT_NOT_AUTHORIZED,
			_("This user is not permitted to approve this action."),
		)

	if not pin_store.has_pin(approver):
		return _deny(
			log.RESULT_NO_PIN,
			_("{0} has no authorization PIN yet. A System Manager can set one on the User record.").format(
				approver
			),
		)

	if not pin_store.verify(approver, pin):
		locked = pin_store.register_failure(approver)
		if locked:
			return _deny(
				log.RESULT_LOCKED_OUT,
				_("Too many failed attempts. Approval is locked for {0} minutes.").format(
					pin_store.lockout_seconds() // 60
				),
			)
		return _deny(log.RESULT_INVALID_PIN, _("Incorrect PIN"))

	pin_store.clear_failures(approver)
	token = grants.issue(action, approver, action_def.binding(context))

	return {
		"authorized": True,
		"grant_token": token,
		"expires_in": grants.GRANT_TTL,
		"approved_by": approver,
	}


@frappe.whitelist()
def set_authorization_pin(user: str, new_pin: str, current_pin: str | None = None) -> dict:
	user = user or frappe.session.user
	pin_store.validate_format(new_pin)

	if user == frappe.session.user:
		if pin_store.has_pin(user) and not pin_store.verify(user, current_pin):
			return {"success": False, "message": _("Current PIN is incorrect")}
	else:
		frappe.has_permission("User", ptype="write", doc=user, throw=True)

	pin_store.set_pin(user, new_pin)
	log.record(action="set_authorization_pin", approver=user, result=log.RESULT_PIN_SET)

	return {"success": True, "message": _("PIN updated")}


@frappe.whitelist()
def clear_authorization_pin(user: str) -> dict:
	"""Remove a user's PIN. System Manager only — this revokes their ability to approve."""
	frappe.only_for("System Manager")

	pin_store.clear_pin(user)
	log.record(action="clear_authorization_pin", approver=user, result=log.RESULT_PIN_SET)

	return {"success": True}


@frappe.whitelist()
def has_authorization_pin(user: str | None = None) -> dict:
	user = user or frappe.session.user
	if user != frappe.session.user:
		frappe.has_permission("User", ptype="read", doc=user, throw=True)

	return {
		"has_pin": pin_store.has_pin(user),
		"pin_length": pin_store.pin_length(),
		"strict_pin_enforced": pin_store.strict_pin_enforced(),
	}
