# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Shared authorization guards for POS Next whitelisted endpoints.

Every non-guest whitelisted endpoint in ``pos_next`` must at minimum call
:func:`ensure_desk_user` so Website/Portal users cannot access POS APIs.
Endpoints scoped to a POS Profile must additionally call
:func:`ensure_pos_user`, and privileged management actions should check
:func:`is_pos_supervisor` or :func:`ensure_pos_supervisor`.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

SUPERVISOR_ROLES: frozenset[str] = frozenset({"Nexus POS Manager", "System Manager"})


def is_pos_supervisor(user: str | None = None) -> bool:
	"""Return True if ``user`` is Administrator or holds a POS supervisor role."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	if user == "Administrator":
		return True
	roles = frappe.get_roles(user) or ()
	return bool(SUPERVISOR_ROLES.intersection(roles))


def ensure_desk_user(user: str | None = None) -> str:
	"""Ensure the caller is an enabled Desk (System User), blocking Guests and Portal users.

	Returns:
		The validated user ID.

	Raises:
		frappe.AuthenticationError: If caller is Guest or unauthenticated.
		frappe.PermissionError: If caller is disabled, missing, or a Website/Portal user.
	"""
	user = user or frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Authentication required"), frappe.AuthenticationError)

	if user == "Administrator":
		return user

	user_info = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
	if not user_info or not cint(user_info.get("enabled")):
		frappe.throw(_("User account is disabled"), frappe.PermissionError)

	if user_info.get("user_type") != "System User":
		frappe.throw(_("Desk user access required"), frappe.PermissionError)

	return user


def ensure_pos_supervisor(user: str | None = None) -> str:
	"""Ensure the caller is an enabled Desk user with a POS supervisor role."""
	user = ensure_desk_user(user)
	if not is_pos_supervisor(user):
		frappe.throw(_("Supervisor permission required"), frappe.PermissionError)
	return user


def ensure_pos_user(pos_profile: str | None, user: str | None = None) -> str:
	"""Ensure the caller is an enabled Desk user assigned to ``pos_profile`` or a supervisor.

	Args:
		pos_profile: POS Profile name to authorize against.
		user: Optional user ID (defaults to ``frappe.session.user``).

	Returns:
		The validated user ID.

	Raises:
		frappe.ValidationError: If ``pos_profile`` is missing.
		frappe.PermissionError: If caller is not assigned to the profile and not a supervisor.
	"""
	user = ensure_desk_user(user)
	if not pos_profile:
		frappe.throw(_("POS Profile is required"), frappe.ValidationError)

	if is_pos_supervisor(user):
		return user

	is_assigned = frappe.db.exists("POS Profile User", {"parent": pos_profile, "user": user})
	if not is_assigned:
		frappe.throw(
			_("You do not have access to POS Profile {0}").format(pos_profile),
			frappe.PermissionError,
		)

	return user
