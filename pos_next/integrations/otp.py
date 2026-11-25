"""Versioned customer email OTP provider contract and registry.

A provider is a duck-typed object (or module) exposing ``name``, ``label``,
``api`` (must equal OTP_PROVIDER_API), ``requires_phone``, ``health()``,
``send(ctx)`` and ``verify(ctx, otp)``. Providers are registered through the
``pos_next_email_otp_providers`` hook as dotted paths to zero-arg factories.

Optional: ``clear(ctx) -> None`` forgets any pending code for ``ctx.customer``
(called on an email change or a verification reset). It is looked up with
``getattr``; a provider without it is valid and ``OTP_PROVIDER_API`` stays 1.
Exceptions from ``clear`` are logged with a fixed text and ignored.

Provider failures are logged with the exception class name only, after the
``except`` block and without Sentry (``utils.log_error_without_telemetry``),
so neither the code, the request body nor frame locals leave the server.

Providers must follow the same rule: inside ``send`` / ``verify`` (and
``clear`` / ``health``) never call ``frappe.log_error`` -- it sends the
request body (which holds the code) to Sentry. Use
``pos_next.utils.log_error_without_telemetry(title, message)`` with a fixed
message (no code, email, phone or response body), outside any ``except``
block.
"""

from __future__ import annotations

from dataclasses import dataclass

import frappe
from frappe import _

from pos_next import utils

OTP_PROVIDER_API = 1
OTP_LENGTH = 6  # digits in a verification code (public contract value)

RESULT_CODES = frozenset(
	{
		# provider codes
		"sent",
		"verified",
		"invalid_otp",
		"expired",
		"rate_limited",
		"not_configured",
		"unavailable",
		"rejected",
		# pass-through codes produced by pos_next itself
		"disabled",
		"busy",
		"invalid_email",
		"email_not_saved",
		"phone_required",
		"invalid_phone",
		"otp_not_required",
	}
)

DEFAULT_PROVIDER = "frappe_email"
_LOG_TITLE = "Customer Email OTP provider"
_REQUIRED_ATTRS = ("name", "label", "api", "requires_phone", "health", "send", "verify")
_CACHE_ATTR = "pos_next_otp_providers"


@dataclass
class OtpContext:
	customer: str
	email: str
	phone: str | None = None
	pos_profile: str | None = None


def _valid(provider) -> bool:
	return (
		all(hasattr(provider, a) for a in _REQUIRED_ATTRS)
		and all(callable(getattr(provider, a)) for a in ("health", "send", "verify"))
		and provider.api == OTP_PROVIDER_API
		and isinstance(provider.name, str)
		and bool(provider.name)
	)


def get_providers() -> dict:
	cached = getattr(frappe.local, _CACHE_ATTR, None)
	if cached is not None:
		return cached

	providers = {}
	for path in frappe.get_hooks("pos_next_email_otp_providers") or []:
		error = None
		try:
			provider = frappe.get_attr(path)()
		except Exception as e:
			error = type(e).__name__
		if error:
			_log(f"Provider factory failed: {path}: {error}")
			continue
		if not _valid(provider):
			_log(f"Invalid email OTP provider from {path}")
			continue
		if provider.name in providers:
			_log(f"Duplicate email OTP provider name '{provider.name}' from {path}")
			continue
		providers[provider.name] = provider

	setattr(frappe.local, _CACHE_ATTR, providers)
	return providers


def get_active_provider(pos_profile: str | None):
	"""Return the provider configured for the profile.

	Returns None when the configured provider is not registered; callers treat
	None as ``not_configured``.
	"""
	name = None
	if pos_profile and frappe.get_meta("POS Settings").has_field("verification_provider"):
		name = frappe.db.get_value(
			"POS Settings", {"pos_profile": pos_profile}, "verification_provider"
		)
	return get_providers().get(name or DEFAULT_PROVIDER)


def _log(message: str) -> None:
	# Logging must never break the caller (or raise a 5xx carrying the request body).
	try:
		utils.log_error_without_telemetry(_LOG_TITLE, message)
	except Exception:
		pass


def call_provider(fn, *args) -> dict:
	unavailable = {"ok": False, "code": "unavailable"}
	error = None
	try:
		result = fn(*args)
	except Exception as e:
		# Only the class name leaves this block: the arguments hold the code.
		error = type(e).__name__
	if error:
		_log(f"Provider call failed: {error}")
		return unavailable
	if not isinstance(result, dict) or "ok" not in result or result.get("code") not in RESULT_CODES:
		_log("Provider returned a malformed result")
		return unavailable
	return result


def can_manage_verification(user: str | None = None) -> bool:
	"""True when the user may write the POS Settings verification fields (permlevel 1).

	Who that is lives only in the DocType's permissions (Role Permissions
	Manager), never in code.
	"""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return 1 in frappe.get_meta("POS Settings").get_permlevel_access("write", user=user)


@frappe.whitelist()
def get_provider_options() -> list[dict]:
	"""Registered providers with their health, for the POS Settings form (admins only)."""
	from pos_next.api.security import ensure_desk_user

	ensure_desk_user()
	if not can_manage_verification():
		frappe.throw(_("Not permitted to manage email verification providers"), frappe.PermissionError)
	options = []
	for provider in get_providers().values():
		health = _call_provider_health(provider)
		options.append({"name": provider.name, "label": provider.label, "health": health})
	return options


def _call_provider_health(provider) -> dict:
	error = None
	try:
		health = provider.health()
		if isinstance(health, dict) and "ok" in health:
			return health
	except Exception as e:
		error = type(e).__name__
	if error:
		_log(f"Provider health check failed: {error}")
	return {"ok": False, "message": _("Health check failed"), "fix_url": None}
