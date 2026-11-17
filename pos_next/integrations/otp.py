"""Versioned customer email OTP provider contract and registry.

A provider is a duck-typed object (or module) exposing ``name``, ``label``,
``api`` (must equal OTP_PROVIDER_API), ``requires_phone``, ``health()``,
``send(ctx)`` and ``verify(ctx, otp)``. Providers are registered through the
``pos_next_email_otp_providers`` hook as dotted paths to zero-arg factories.

Optional: ``clear(ctx) -> None`` forgets any pending code for ``ctx.customer``
(called on an email change or a verification reset). It is looked up with
``getattr``; a provider without it is valid and ``OTP_PROVIDER_API`` stays 1.
Exceptions from ``clear`` are logged with a fixed text and ignored.
"""

from __future__ import annotations

from dataclasses import dataclass

import frappe

OTP_PROVIDER_API = 1

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
		try:
			provider = frappe.get_attr(path)()
		except Exception:
			frappe.log_error(frappe.get_traceback(), _LOG_TITLE)
			continue
		if not _valid(provider):
			frappe.log_error(f"Invalid email OTP provider from {path}", _LOG_TITLE)
			continue
		if provider.name in providers:
			frappe.log_error(f"Duplicate email OTP provider name '{provider.name}' from {path}", _LOG_TITLE)
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


def call_provider(fn, *args) -> dict:
	unavailable = {"ok": False, "code": "unavailable"}
	try:
		result = fn(*args)
	except Exception:
		frappe.log_error(frappe.get_traceback(), _LOG_TITLE)
		return unavailable
	if not isinstance(result, dict) or "ok" not in result or result.get("code") not in RESULT_CODES:
		frappe.log_error("Provider returned a malformed result", _LOG_TITLE)
		return unavailable
	return result


@frappe.whitelist()
def get_provider_options() -> list[dict]:
	frappe.has_permission("POS Settings", "write", throw=True)
	options = []
	for provider in get_providers().values():
		health = _call_provider_health(provider)
		options.append({"name": provider.name, "label": provider.label, "health": health})
	return options


def _call_provider_health(provider) -> dict:
	try:
		health = provider.health()
		if isinstance(health, dict) and "ok" in health:
			return health
	except Exception:
		frappe.log_error(frappe.get_traceback(), _LOG_TITLE)
	return {"ok": False, "message": "Health check failed", "fix_url": None}
