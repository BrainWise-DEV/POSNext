# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Shared fixtures for the authorization test suite.

Registers a dummy action at import time, shared across every test file below so they
all exercise the same generic action rather than each registering their own. Import
order across files doesn't matter: module-level code runs once per process no matter
how many test files import this one.

All fixtures are prefixed ``_PNXT_AUTH_`` so they can be cleaned up safely.
"""

import frappe

from pos_next.authorization import registry
from pos_next.authorization.registry import Action

PREFIX = "_PNXT_AUTH_"
# Frappe lowercases user ids on insert, so these must already be lowercase or every
# comparison against a stored value fails.
_U = PREFIX.lower()
CASHIER = f"{_U}cashier@example.com"
MANAGER = f"{_U}manager@example.com"
OUTSIDER = f"{_U}outsider@example.com"
ROLE = f"{PREFIX}Approver"

GOOD_PIN = "8317"
OTHER_PIN = "2946"

# action is a hardcoded Select on POS Authorization Rule (see pos_authorization_rule.json)
# and only ships two real values. A test-only action needs the "_T-" prefix Frappe's own
# Select validation already exempts from the options check when frappe.flags.in_test is
# set (frappe.model.base_document.BaseDocument._validate_selects) — the same convention
# core uses for its own auto-generated test records. Without that prefix, saving a rule
# for a made-up action would fail Select validation before ever reaching our own code.
DUMMY_ACTION = "_T-pnxt-dummy-action"

registry.register(
	Action(
		name=DUMMY_ACTION,
		binding=lambda ctx: {"widget": ctx.get("widget"), "amount": ctx.get("amount")},
	)
)


def make_user(email: str, roles: list[str] | None = None) -> str:
	if not frappe.db.exists("User", email):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"enabled": 1,
			}
		)
		user.insert(ignore_permissions=True)
	else:
		user = frappe.get_doc("User", email)

	for role in roles or []:
		if not any(r.role == role for r in user.get("roles") or []):
			user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	return email


def make_role(name: str) -> str:
	if not frappe.db.exists("Role", name):
		frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 0}).insert(
			ignore_permissions=True
		)
	return name


def make_rule(action: str, approvers: list[dict], **kwargs) -> object:
	frappe.db.delete("POS Authorization Rule", {"action": action})
	rule = frappe.get_doc(
		{
			"doctype": "POS Authorization Rule",
			"action": action,
			"enabled": 1,
			"allow_self_approval": kwargs.get("allow_self_approval", 1),
			"pos_profile": kwargs.get("pos_profile"),
			"approvers": approvers,
		}
	)
	rule.insert(ignore_permissions=True)
	return rule
