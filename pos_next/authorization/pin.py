# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""POS authorization PIN — a hashed, POS-only secret.

Key Security Properties:
    - Session Isolation: Maintains a distinct __Auth record from desk login
      passwords. Grants zero desk access and is verified exclusively by
      :mod:`pos_next.authorization.gate`.
    - Credential Decoupling: Updating the PIN does not impact login passwords,
      and vice versa.
    - Access Containment: Compromise via shoulder-surfing yields no backend
      or desk access.

"""

from itertools import pairwise

import frappe
from frappe import _
from frappe.query_builder import Table
from frappe.utils import cint
from frappe.utils.password import check_password, update_password

PIN_FIELD = "pos_authorization_pin"

SETTINGS_DOCTYPE = "POS Authorization Settings"

#: Used whenever POS Authorization Settings hasn't been saved yet, or a field on it is
#: left blank. Keeps the module secure and usable out of the box, with no setup step.
DEFAULT_PIN_LENGTH = 4
DEFAULT_MAX_FAILURES = 5
DEFAULT_LOCKOUT_MINUTES = 15


def _settings():
	"""The POS Authorization Settings singleton, cached like any other Frappe single."""
	return frappe.get_cached_doc(SETTINGS_DOCTYPE)


def pin_length() -> int:
	"""Digits an authorization PIN must have."""
	return cint(_settings().get("pin_length")) or DEFAULT_PIN_LENGTH


def max_failures() -> int:
	"""Consecutive wrong PINs before an approver is locked out."""
	return cint(_settings().get("max_failures")) or DEFAULT_MAX_FAILURES


def lockout_seconds() -> int:
	"""How long a lockout lasts, and the window over which failures accumulate."""
	minutes = cint(_settings().get("lockout_minutes")) or DEFAULT_LOCKOUT_MINUTES
	return minutes * 60


def strict_pin_enforced() -> bool:
	"""Whether trivially guessable PINs (repeats, straight runs) should be refused.

	Unlike the numeric settings above, an unset value here must mean "on" — a blank
	field should never silently weaken the default, so this doesn't fold falsy into a
	fallback the way ``pin_length()``/``max_failures()`` do.
	"""
	value = _settings().get("enforce_strict_pin")
	return True if value is None else bool(cint(value))


def validate_format(pin: str) -> None:
	"""Raise if ``pin`` is not an acceptable PIN. Called before any write."""
	pin = (pin or "").strip()
	length = pin_length()

	if not pin.isdigit():
		frappe.throw(_("PIN must contain digits only"), title=_("Invalid PIN"))

	if len(pin) != length:
		frappe.throw(_("PIN must be exactly {0} digits").format(length), title=_("Invalid PIN"))

	if strict_pin_enforced() and _is_trivial(pin):
		frappe.throw(
			_("That PIN is too easy to guess. Avoid repeated digits and simple sequences."),
			title=_("Invalid PIN"),
		)


def _is_trivial(pin: str) -> bool:
	"""Every digit the same, or a straight ascending/descending run.

	Algorithmic rather than a fixed list of "bad" PINs, so it isn't tied to any one PIN
	length and doesn't need updating if ``pin_length`` above changes. Covers e.g. 0000,
	1234, 4321, and the wrap-around cases 7890 and 0987 (7-8-9-0 and 0-9-8-7 are each a
	straight run once you allow 9 to roll over to 0).
	"""
	digits = [int(ch) for ch in pin]

	if len(set(digits)) == 1:
		return True

	steps = list(pairwise(digits))
	ascending = all((b - a) % 10 == 1 for a, b in steps)
	descending = all((a - b) % 10 == 1 for a, b in steps)
	return ascending or descending


def has_pin(user: str) -> bool:
	"""True when ``user`` has an authorization PIN set."""
	if not user:
		return False

	Auth = Table("__Auth")
	rows = (
		frappe.qb.from_(Auth)
		.select(Auth.name)
		.where(
			(Auth.doctype == "User")
			& (Auth.name == user)
			& (Auth.fieldname == PIN_FIELD)
			& (Auth.encrypted == 0)
		)
		.limit(1)
	).run()

	return bool(rows)


def users_with_pin(users: set[str] | list[str]) -> set[str]:
	"""Filter ``users`` down to those who have a PIN set, in one query.

	Returns the **caller's** spelling of each id, not the one stored in ``__Auth``.
	MariaDB matches these case-insensitively while Python set arithmetic does not, and
	``__Auth`` can disagree on case with the table the caller resolved from (``Has Role``,
	say). Echoing the input keeps callers like ``get_authorization_readiness`` from
	reporting the same person as both ready and missing a PIN.
	"""
	users = [u for u in (users or []) if u]
	if not users:
		return set()

	Auth = Table("__Auth")
	rows = (
		frappe.qb.from_(Auth)
		.select(Auth.name)
		.where(
			(Auth.doctype == "User")
			& (Auth.fieldname == PIN_FIELD)
			& (Auth.encrypted == 0)
			& (Auth.name.isin(users))
		)
	).run(pluck=True)

	found = {str(row).casefold() for row in (rows or [])}
	return {user for user in users if user.casefold() in found}


def set_pin(user: str, pin: str) -> None:
	"""Store ``pin`` for ``user``, hashed. Clears any active lockout."""
	validate_format(pin)
	update_password(user, pin, doctype="User", fieldname=PIN_FIELD)
	clear_failures(user)


def clear_pin(user: str) -> None:
	"""Remove ``user``'s PIN. They can no longer approve anything."""
	Auth = Table("__Auth")
	(
		frappe.qb.from_(Auth)
		.delete()
		.where((Auth.doctype == "User") & (Auth.name == user) & (Auth.fieldname == PIN_FIELD))
	).run()
	clear_failures(user)


def verify(user: str, pin: str) -> bool:
	"""True when ``pin`` is ``user``'s PIN.

	Never raises ``frappe.AuthenticationError``. Frappe's request error handler calls
	``login_manager.clear_cookies()`` for that exception type, which on a wrong PIN would
	destroy the *cashier's* session because the approver mistyped. See
	``pos_next/api/auth.py`` for the same landmine.
	"""
	if not user or not pin:
		return False

	try:
		# delete_tracker_cache=False: a PIN check must not clear the user's failed *login*
		# tracking. Those are separate security counters with a separate lockout.
		check_password(user, pin, doctype="User", fieldname=PIN_FIELD, delete_tracker_cache=False)
		return True
	except frappe.AuthenticationError:
		return False


def _fail_key(user: str) -> str:
	return f"pos_auth_pin_fail:{user}"


def _lock_key(user: str) -> str:
	return f"pos_auth_pin_lock:{user}"


def is_locked_out(user: str) -> bool:
	"""True when ``user`` has failed too often and may not approve for now."""
	cache = frappe.cache()
	try:
		return bool(cache.get(cache.make_key(_lock_key(user))))
	except Exception:
		return False


def register_failure(user: str) -> bool:
	"""Count a failed attempt. Returns True when this attempt triggered a lockout."""
	cache = frappe.cache()
	try:
		lockout = lockout_seconds()
		key = cache.make_key(_fail_key(user))
		count = cint(cache.incr(key))
		if count == 1:
			cache.expire(key, lockout)

		if count >= max_failures():
			cache.set(cache.make_key(_lock_key(user)), b"1", ex=lockout)
			cache.delete(key)
			return True
	except Exception:
		frappe.log_error(frappe.get_traceback(), "POS Authorization Lockout Error")

	return False


def clear_failures(user: str) -> None:
	"""Reset the failure counter and any lockout for ``user``."""
	cache = frappe.cache()
	try:
		cache.delete(cache.make_key(_fail_key(user)))
		cache.delete(cache.make_key(_lock_key(user)))
	except Exception:
		frappe.log_error(frappe.get_traceback(), "POS Authorization Lockout Error")
