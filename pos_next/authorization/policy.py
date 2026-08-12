# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Which rule applies, and who may approve under it.

A ``POS Authorization Rule`` carries a child table of approvers. Each row names either a
Role (anyone holding it) or a specific User, and may carry a ``condition`` expression.
Rows are **OR-ed**: a user is eligible if any row admits them. So one rule can read
"any Nexus POS Manager, plus ahmed@example.com, plus Store Supervisor but only under
50,000".

Conditions follow the same shape as ``Notification Recipient``: ``frappe.safe_eval``,
validated when the rule is saved and re-evaluated at approval time.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

RULE_DOCTYPE = "POS Authorization Rule"

APPROVER_TYPE_ROLE = "Role"
APPROVER_TYPE_USER = "User"


def resolve_rule(action_name: str, pos_profile: str | None = None):
	"""The rule governing ``action_name`` here, or ``None`` when nothing is configured.

	A rule naming this POS Profile wins over a catch-all rule (blank ``pos_profile``), so
	one site can gate a single till more tightly than the rest.

	Returning ``None`` is the common case on existing installations and means the action
	proceeds exactly as it did before the gate existed.
	"""
	rules = frappe.get_all(
		RULE_DOCTYPE,
		filters={"action": action_name, "enabled": 1},
		fields=["name", "pos_profile"],
		order_by="modified desc",
	)
	if not rules:
		return None

	specific = [r for r in rules if r.pos_profile and r.pos_profile == pos_profile]
	catch_all = [r for r in rules if not r.pos_profile]

	chosen = specific or catch_all
	if not chosen:
		return None

	return frappe.get_cached_doc(RULE_DOCTYPE, chosen[0].name)


def eligible_approvers(rule, context: dict | None = None) -> set[str]:
	"""Every enabled user admitted by any row of ``rule``."""
	users: set[str] = set()

	for row in rule.get("approvers") or []:
		if row.condition and not eval_condition(row.condition, context):
			continue

		if row.approver_type == APPROVER_TYPE_ROLE and row.role:
			# Already filtered to enabled users by the join in users_with_role() —
			# checking again per user here would be one extra query per role member
			# for a fact the SQL already guarantees.
			users |= users_with_role(row.role)
		elif row.approver_type == APPROVER_TYPE_USER and row.user and _is_enabled(row.user):
			users.add(row.user)

	return users


def is_approver(rule, user: str, context: dict | None = None) -> bool:
	"""Whether ``user`` may approve under ``rule`` right now."""
	if not user:
		return False

	if not rule.get("allow_self_approval") and user == frappe.session.user:
		return False

	return user in eligible_approvers(rule, context)


def describe_approvers(rule) -> str:
	"""Readable list of who can approve, for the denial message."""
	parts = []
	for row in rule.get("approvers") or []:
		if row.approver_type == APPROVER_TYPE_ROLE and row.role:
			parts.append(row.role)
		elif row.approver_type == APPROVER_TYPE_USER and row.user:
			parts.append(row.user)

	return ", ".join(dict.fromkeys(parts))


def validate_approvers(rule) -> None:
	"""Reject a rule with no approvers — it would block the action for everyone,
	permanently — and normalize each row to match its own approver_type.
	"""
	rows = rule.get("approvers") or []
	if not rows:
		frappe.throw(
			_("Add at least one approver, otherwise this action can never be authorized."),
			title=_("No Approvers"),
		)

	for row in rows:
		if row.approver_type == APPROVER_TYPE_ROLE:
			row.user = None
			if not row.role:
				frappe.throw(_("Row {0}: select a Role").format(row.idx))
		elif row.approver_type == APPROVER_TYPE_USER:
			row.role = None
			if not row.user:
				frappe.throw(_("Row {0}: select a User").format(row.idx))


def users_with_role(role: str) -> set[str]:
	"""Enabled users holding ``role``."""
	HasRole = frappe.qb.DocType("Has Role")
	User = frappe.qb.DocType("User")

	rows = (
		frappe.qb.from_(HasRole)
		.inner_join(User)
		.on(User.name == HasRole.parent)
		.select(HasRole.parent)
		.where((HasRole.role == role) & (HasRole.parenttype == "User") & (User.enabled == 1))
	).run(pluck=True)

	return set(rows or [])


def _is_enabled(user: str) -> bool:
	return bool(frappe.db.get_value("User", user, "enabled"))


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------


def build_condition_context(context: dict | None = None) -> dict:
	"""Names available inside a row ``condition``."""
	context = context or {}

	# frappe._dict returns None for missing keys, so `doc.customer_group` in a condition
	# is safe both at validation time (empty doc) and at runtime.
	doc = context.get("doc") or frappe._dict()
	if not isinstance(doc, frappe._dict):
		doc = frappe._dict(doc)

	return {
		"doc": doc,
		"amount": flt(context.get("amount")),
		"pos_profile": context.get("pos_profile"),
		"customer": context.get("customer"),
		"requested_by": frappe.session.user,
		"nowdate": nowdate,
		"getdate": getdate,
	}


def eval_condition(condition: str, context: dict | None = None, throw: bool = False) -> bool:
	"""Evaluate a row condition.

	A condition that blows up at runtime **skips its row** rather than breaking the gate —
	one bad expression should not make every refund impossible. Set ``throw=True`` when
	validating at save time, where failing loudly is the whole point.
	"""
	if not condition:
		return True

	try:
		return bool(frappe.safe_eval(condition, None, build_condition_context(context)))
	except Exception:
		if throw:
			raise
		frappe.log_error(frappe.get_traceback(), "POS Authorization Condition Error")
		return False


def validate_conditions(rule) -> None:
	"""Reject invalid conditions when the rule is saved, not at the till.

	A broken expression discovered mid-refund, with a customer waiting, is the worst
	possible time to find out.
	"""
	sample = {
		"doc": frappe._dict(),
		"amount": 0,
		"pos_profile": rule.get("pos_profile"),
		"customer": None,
	}

	for row in rule.get("approvers") or []:
		if not row.condition:
			continue
		try:
			eval_condition(row.condition, sample, throw=True)
		except Exception:
			frappe.throw(
				_("The condition {0} in row {1} is invalid").format(frappe.bold(row.condition), row.idx),
				title=_("Invalid Condition"),
			)
