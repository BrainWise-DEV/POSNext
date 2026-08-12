# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Short-lived authorization grants.

A grant is minted when an approver proves their PIN, and is spent when the gate lets an
action through. It is deliberately narrow: bound to one action, one requester and one
set of binding values, and dead within :data:`GRANT_TTL` seconds.

**Consumption is compare-and-set, not delete.** Redis is not transactional with MariaDB.
If a grant were deleted in ``before_submit`` and a later ``on_submit`` handler threw —
wallet reversal, Magento LP and one-time offer usage all run there — the database would
roll back with the grant already gone, and the approver would have to walk back to the
till and approve a second time. Binding the grant to the document instead makes a retry
of *that* document succeed while any other document still fails.
"""

import pickle
import secrets

import frappe
from frappe.utils import flt

GRANT_TTL = 180

_AMOUNT_TOLERANCE = 0.01

_KEY_PREFIX = "pos_auth_grant:"


def _key(token: str) -> bytes:
	return frappe.cache().make_key(f"{_KEY_PREFIX}{token}")


def _read(key: bytes) -> dict | None:
	try:
		raw = frappe.cache().get(key)
	except Exception:
		return None
	return pickle.loads(raw) if raw else None


def _write(key: bytes, grant: dict) -> None:
	frappe.cache().set(key, pickle.dumps(grant), ex=GRANT_TTL)


def issue(action_name: str, approver: str, binding: dict) -> str:
	"""Mint a grant for ``action_name``, approved by ``approver``. Returns the token."""
	token = secrets.token_urlsafe(32)

	_write(
		_key(token),
		{
			"action": action_name,
			"approver": approver,
			"binding": binding or {},
			"requested_by": frappe.session.user,
			"consumed_by": None,
		},
	)

	return token


def consume(token: str, action_name: str, binding: dict, reference: str | None = None) -> dict | None:
	"""Spend ``token`` for this action and binding, or return ``None``.

	``reference`` is the thing being authorized — a document name, usually. The first
	successful consume pins the grant to it; later consumes succeed only for that same
	reference, so a retry works and a second document does not.
	"""
	if not token:
		return None

	key = _key(token)
	grant = _read(key)
	if not grant:
		return None

	if grant.get("action") != action_name:
		return None

	# The grant belongs to the session that asked for it. A token leaked to another
	# terminal is useless there.
	if grant.get("requested_by") != frappe.session.user:
		return None

	consumed_by = grant.get("consumed_by")
	if consumed_by is not None and consumed_by != reference:
		return None

	if not binding_matches(grant.get("binding") or {}, binding or {}):
		return None

	grant["consumed_by"] = reference
	_write(key, grant)

	return grant


def revoke(token: str) -> None:
	"""Drop a grant early. Not used in the normal flow; handy for tests and cleanup."""
	if token:
		frappe.cache().delete(_key(token))


def binding_matches(approved: dict, actual: dict) -> bool:
	"""Whether the act being attempted is the one that was approved.

	Action-agnostic: every key in ``approved`` must equal its counterpart, except
	``amount``, which may be **lower** than approved but never higher. Dropping a line
	after approval is fine; adding one needs a fresh approval.
	"""
	for field, approved_value in (approved or {}).items():
		actual_value = (actual or {}).get(field)

		if field == "amount":
			if flt(actual_value) > flt(approved_value) + _AMOUNT_TOLERANCE:
				return False
			continue

		# Treat "" and None as the same absence, so a blank return_against matches.
		if (approved_value or None) != (actual_value or None):
			return False

	return True
