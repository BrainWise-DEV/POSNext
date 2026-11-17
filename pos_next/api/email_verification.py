# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""
Customer email OTP verification (cashier initiated).

Sends a one-time code to the customer's saved email through the email OTP
provider configured for the POS Profile (``pos_next.integrations.otp``) and
records the result on the Customer.

Design notes
------------
* Provider-agnostic: pos_next never imports a client app. Providers register
  through the ``pos_next_email_otp_providers`` hook; every provider call goes
  through ``otp.call_provider`` so a crash or malformed answer is ``unavailable``.
* Rate limits (resend cooldown, sends per hour, verify attempts per issued
  code), the per-customer lock and the audit trail live here, so every provider
  gets them.
* The phone number is read from ``Customer.mobile_no`` server side, never from
  the client, and only when the provider needs it. It is normalised to E.164
  with ``phonenumbers`` using the profile's ``default_phone_country``.
* The OTP is never logged, stored in Error Log / Comments, or returned.
* Message contract: the provider's own text reaches the cashier only for code
  ``rejected``; every other code uses pos_next text. Provider ``health()`` text
  is never shown to the cashier.
* The feature is gated by ``POS Settings.enable_customer_email_verification``
  (default off) — except for Friends & Family members (optional POSNext
  Promotions app), who must have a verified email for F&F and can therefore
  always be verified.
"""

import json
import re
import time
from dataclasses import dataclass

import frappe
import phonenumbers
from frappe import _
from frappe.utils import cint, now_datetime

from pos_next.integrations import otp
from pos_next.utils import validate_pos_profile_access

DEFAULT_OTP_TTL = 900  # seconds
DEFAULT_RESEND_COOLDOWN = 60  # seconds between sends per customer
DEFAULT_MAX_SENDS_PER_HOUR = 5
MAX_VERIFY_ATTEMPTS = 10  # per issued code window
HOUR = 3600
LOCK_TIMEOUT = 30

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
OTP_RE = re.compile(r"^\d{6}$")

VERIFICATION_FIELDS = (
	"custom_email_verified",
	"custom_email_verified_on",
	"custom_email_verified_by",
	"custom_verified_email",
	"custom_email_verified_via",
)

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


# ---------------------------------------------------------------------------
# Messages / responses
# ---------------------------------------------------------------------------

def _messages():
	# Function (not a constant) so strings are translated at call time.
	return {
		"phone_required": _("Customer has no phone number."),
		"invalid_phone": _("Invalid phone number."),
		"invalid_email": _("Enter a valid email address."),
		"rejected": _("The verification service rejected this request."),
		"unavailable": _("Could not send the code, please try again."),
		"expired": _("Code expired. Request a new one."),
		"invalid_otp": _("Wrong code (or email changed)."),
		"not_configured": _("Email verification is not set up. Ask an administrator."),
		"disabled": _("Email verification is disabled."),
		"email_not_saved": _("Save the customer's email before verifying it."),
		"busy": _("Another request is in progress. Please wait."),
	}


def _result(ok, code, message=None, **extra):
	out = {"ok": bool(ok), "code": code, "message": message or _messages().get(code) or code}
	out.update({k: v for k, v in extra.items() if v is not None})
	return out


def _rate_limited(retry_after):
	retry_after = max(1, cint(retry_after))
	return _result(
		False,
		"rate_limited",
		_("Too many attempts. Try again in {0}s.").format(retry_after),
		retry_after=retry_after,
	)


def _safe_message(message):
	return (str(message or "").strip())[:200]


def _failure(result, action):
	"""Map a failed provider result to the cashier-facing result.

	Only ``rejected`` carries the provider's own text; everything else uses
	pos_next text. Unknown or inconsistent codes become ``unavailable``.
	"""
	code = result.get("code")
	if code == "rejected":
		return _result(False, "rejected", _safe_message(result.get("message")) or None)
	if code == "rate_limited":
		return _rate_limited(result.get("retry_after") or 1)
	if code == "unavailable" or code not in ("expired", "invalid_otp", "not_configured"):
		message = (
			_("Could not verify the code, please try again.") if action == "verify" else None
		)
		return _result(False, "unavailable", message)
	return _result(False, code)


# ---------------------------------------------------------------------------
# Settings (per POS Profile)
# ---------------------------------------------------------------------------

@dataclass
class _OtpSettings:
	otp_ttl_seconds: int = DEFAULT_OTP_TTL
	otp_resend_cooldown: int = DEFAULT_RESEND_COOLDOWN
	otp_max_sends_per_hour: int = DEFAULT_MAX_SENDS_PER_HOUR
	default_phone_country: str | None = None
	placeholder_email_domain: str | None = None


def _positive_int(value, default):
	try:
		value = int(value)
	except (TypeError, ValueError):
		return default
	return value if value > 0 else default


def _otp_settings(pos_profile):
	"""OTP limits for the profile's enabled POS Settings row; blank values use the defaults."""
	row = None
	if pos_profile:
		row = frappe.db.get_value(
			"POS Settings",
			{"pos_profile": pos_profile, "enabled": 1},
			[
				"otp_ttl_seconds",
				"otp_resend_cooldown",
				"otp_max_sends_per_hour",
				"default_phone_country",
				"placeholder_email_domain",
			],
			as_dict=True,
		)
	row = row or {}
	return _OtpSettings(
		otp_ttl_seconds=_positive_int(row.get("otp_ttl_seconds"), DEFAULT_OTP_TTL),
		otp_resend_cooldown=_positive_int(row.get("otp_resend_cooldown"), DEFAULT_RESEND_COOLDOWN),
		otp_max_sends_per_hour=_positive_int(row.get("otp_max_sends_per_hour"), DEFAULT_MAX_SENDS_PER_HOUR),
		default_phone_country=row.get("default_phone_country") or None,
		placeholder_email_domain=(row.get("placeholder_email_domain") or "").strip() or None,
	)


# ---------------------------------------------------------------------------
# Normalisation / validation helpers
# ---------------------------------------------------------------------------

def _country_code(country):
	"""ISO 3166 alpha-2 code for a Country name (the Link value), or None."""
	if not country:
		return None
	code = str(frappe.db.get_value("Country", country, "code") or "").strip().upper()
	return code or None


def normalize_phone(value, country):
	"""Return the number in E.164 (e.g. ``+442079460958``) or None when invalid.

	``country`` is a Country name used for numbers without a ``+`` prefix.
	"""
	if value is None:
		return None
	text = str(value).translate(_ARABIC_DIGITS).strip()
	if not text:
		return None
	try:
		number = phonenumbers.parse(text, _country_code(country))
	except phonenumbers.NumberParseException:
		return None
	if not phonenumbers.is_valid_number(number):
		return None
	return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def is_placeholder_email(email, pos_profile=None):
	"""True when the email's domain equals the profile's ``placeholder_email_domain``."""
	domain = (_otp_settings(pos_profile).placeholder_email_domain or "").lstrip("@").lower()
	if not domain:
		return False
	return (email or "").strip().lower().rpartition("@")[2] == domain


def _clean_email(email, pos_profile=None):
	email = (email or "").strip()
	if not email or not EMAIL_RE.match(email) or is_placeholder_email(email, pos_profile):
		return None
	return email


def mask_phone(phone):
	phone = phone or ""
	return phone[:4] + "*" * max(0, len(phone) - 7) + phone[-3:] if len(phone) > 7 else "***"


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

def is_feature_enabled(pos_profile=None):
	"""POS Settings flag (per POS Profile). Without a profile: any enabled row."""
	filters = {"enabled": 1, "enable_customer_email_verification": 1}
	if pos_profile:
		filters["pos_profile"] = pos_profile
	try:
		return bool(frappe.db.exists("POS Settings", filters))
	except Exception:
		return False


def _is_ff_member(customer, pos_profile=None):
	"""Friends & Family member per POSNext Promotions (optional app); False when absent."""
	if not customer or "posnext_promotions" not in frappe.get_installed_apps():
		return False
	try:
		check = frappe.get_attr(
			"posnext_promotions.promotions.friends_and_family_eligibility.is_customer_ff_member"
		)
	except Exception:
		return False
	try:
		return bool(check(customer, pos_profile=pos_profile))
	except Exception:
		_log_unexpected("Friends & Family membership check failed")
		return False


def is_verification_allowed(customer, pos_profile=None):
	"""POS switch on, or the customer is an F&F member (verification is mandatory for F&F)."""
	return is_feature_enabled(pos_profile) or _is_ff_member(customer, pos_profile)


# ---------------------------------------------------------------------------
# Rate limiting (frappe cache)
# ---------------------------------------------------------------------------

def _cache():
	return frappe.cache() if callable(frappe.cache) else frappe.cache


def _state_key(customer):
	return f"pos_next:email_otp:state:{customer}"


def _load_state(customer):
	raw = _cache().get_value(_state_key(customer))
	if isinstance(raw, (str, bytes)):
		try:
			raw = json.loads(raw)
		except ValueError:
			raw = None
	state = raw if isinstance(raw, dict) else {}
	state.setdefault("sends", [])
	state.setdefault("attempts", 0)
	state.setdefault("attempts_reset_at", 0)
	return state


def _code_ttl(state, ttl):
	"""Effective life of the issued code: the TTL stored at send wins over a shorter one now."""
	return max(cint(ttl), cint(state.get("code_ttl")))


def _save_state(customer, state, ttl=DEFAULT_OTP_TTL):
	# Must outlive both the hourly send window and the issued code's TTL (stored at
	# send), or the attempt counter would vanish while the code is still valid.
	_cache().set_value(
		_state_key(customer), json.dumps(state), expires_in_sec=max(HOUR, _code_ttl(state, ttl)) + 60
	)


def _send_gate(state, now, settings):
	"""Return retry_after seconds if sending is blocked, else 0."""
	sends = [t for t in state["sends"] if now - t < HOUR]
	state["sends"] = sends
	if sends:
		wait = settings.otp_resend_cooldown - (now - max(sends))
		if wait > 0:
			return int(wait) + 1
	if len(sends) >= settings.otp_max_sends_per_hour:
		return int(HOUR - (now - min(sends))) + 1
	return 0


class _Lock:
	"""Best-effort per-customer lock against double clicks."""

	def __init__(self, customer):
		self.customer = customer
		self.lock = None
		self.acquired = False

	def __enter__(self):
		try:
			self.lock = _cache().lock(f"pos_next:email_otp:lock:{self.customer}", timeout=LOCK_TIMEOUT)
			self.acquired = bool(self.lock.acquire(blocking=False))
		except Exception:
			# Redis lock unavailable: fall back to the cooldown/attempt counters only.
			self.lock = None
			self.acquired = True
		return self

	def __exit__(self, *exc):
		if self.lock is not None and self.acquired:
			try:
				self.lock.release()
			except Exception:
				pass
		return False


# ---------------------------------------------------------------------------
# Common checks
# ---------------------------------------------------------------------------

def _provider_healthy(provider):
	# health() returns {ok, message, fix_url} (no result code), so it is not routed
	# through otp.call_provider; its message is for admins only and is dropped here.
	return otp._call_provider_health(provider).get("ok") is True


def _prepare(customer, email, pos_profile):
	"""Run checks common to send/verify. Returns (ctx, provider, settings, error_result)."""
	if not customer:
		frappe.throw(_("Customer is required"))
	if pos_profile:
		# The profile decides limits and provider; a caller must not pick another one.
		validate_pos_profile_access(pos_profile, frappe.PermissionError)
	if not is_verification_allowed(customer, pos_profile):
		return None, None, None, _result(False, "disabled")
	if not frappe.has_permission("Customer", "write", customer):
		frappe.throw(_("You don't have permission to verify this customer's email"), frappe.PermissionError)

	doc = frappe.db.get_value("Customer", customer, ["name", "mobile_no", "email_id"], as_dict=True)
	if not doc:
		frappe.throw(_("Customer {0} not found").format(customer), frappe.DoesNotExistError)

	settings = _otp_settings(pos_profile)
	saved_email = (doc.get("email_id") or "").strip()
	if _clean_email(saved_email, pos_profile) is None:
		return None, None, None, _result(False, "invalid_email")
	if email and (email or "").strip().lower() != saved_email.lower():
		return None, None, None, _result(False, "email_not_saved")

	provider = otp.get_active_provider(pos_profile)
	if provider is None or not _provider_healthy(provider):
		return None, None, None, _result(False, "not_configured")

	phone = None
	if provider.requires_phone:
		phone_raw = (doc.get("mobile_no") or "").strip()
		if not phone_raw:
			return None, None, None, _result(False, "phone_required")
		phone = normalize_phone(phone_raw, settings.default_phone_country)
		if not phone:
			return None, None, None, _result(False, "invalid_phone")

	ctx = otp.OtpContext(customer=customer, email=saved_email, phone=phone, pos_profile=pos_profile)
	return ctx, provider, settings, None


def _audit(customer, action, code, email, phone):
	"""Customer comment audit trail. Never contains the OTP."""
	try:
		text = (
			f"Email verification {action}: {code} | email={email} | phone={mask_phone(phone)} "
			f"| by={frappe.session.user}"
		)
		frappe.get_doc("Customer", customer).add_comment("Info", text)
	except Exception:
		# Audit must never break the flow; intentionally not logging details.
		pass


# ---------------------------------------------------------------------------
# Whitelisted API
# ---------------------------------------------------------------------------

@frappe.whitelist(methods=["POST"])
def send_email_otp(customer, email=None, pos_profile=None):
	"""Send a verification code to the customer's saved email."""
	ctx, provider, settings, err = _prepare(customer, email, pos_profile)
	if err:
		return err

	with _Lock(customer) as lock:
		if not lock.acquired:
			return _result(False, "busy")

		now = time.time()
		state = _load_state(customer)
		retry_after = _send_gate(state, now, settings)
		if retry_after:
			return _rate_limited(retry_after)

		# Every call that reaches the provider counts toward the cooldown and the
		# hourly cap, whatever the outcome, so failures cannot bypass the limits.
		result = otp.call_provider(provider.send, ctx)
		state["sends"].append(now)
		ok = result.get("ok") is True
		code = result.get("code")

		if ok and code == "sent":
			state["attempts"] = 0
			state["attempts_reset_at"] = now
			state["code_ttl"] = settings.otp_ttl_seconds
			_save_state(customer, state, settings.otp_ttl_seconds)
			_audit(customer, "send", "sent", ctx.email, ctx.phone)
			return _result(
				True,
				"sent",
				_("Verification code sent by email."),
				expires_in=settings.otp_ttl_seconds,
				resend_in=max(cint(result.get("retry_after")), settings.otp_resend_cooldown),
			)

		_save_state(customer, state, settings.otp_ttl_seconds)

		if ok and code == "otp_not_required":
			_audit(customer, "send", "otp_not_required", ctx.email, ctx.phone)
			return _result(
				True,
				"otp_not_required",
				_("No verification code is needed for this email."),
				otp_required=False,
			)

		out = _failure(result if not ok else {"code": "unavailable"}, "send")
		_audit(customer, "send", out["code"], ctx.email, ctx.phone)
		return out


@frappe.whitelist(methods=["POST"])
def verify_email_otp(customer, otp, email=None, pos_profile=None):
	"""Verify the 6-digit code. Success only when the provider answers ok + ``verified``."""
	code_in = str(otp or "").translate(_ARABIC_DIGITS).strip()
	ctx, provider, settings, err = _prepare(customer, email, pos_profile)
	if err:
		return err

	if not OTP_RE.match(code_in):
		return _result(False, "invalid_otp")

	with _Lock(customer) as lock:
		if not lock.acquired:
			return _result(False, "busy")

		now = time.time()
		state = _load_state(customer)
		if state["attempts"] >= MAX_VERIFY_ATTEMPTS:
			remaining = _code_ttl(state, settings.otp_ttl_seconds) - (now - state["attempts_reset_at"])
			if remaining <= 0:
				# The locked-out code is dead: only a new code (which resets attempts) helps.
				return _result(False, "expired")
			return _rate_limited(remaining)
		# Count the attempt before asking the provider, so a crash cannot skip it.
		state["attempts"] += 1
		_save_state(customer, state, settings.otp_ttl_seconds)

		result = _call_verify(provider, ctx, code_in)

		if result.get("ok") is True and result.get("code") == "verified":
			_mark_verified(customer, ctx.email, provider.name)
			state["attempts"] = 0
			_save_state(customer, state, settings.otp_ttl_seconds)
			_audit(customer, "verify", "verified", ctx.email, ctx.phone)
			return _result(True, "verified", _("Email verified"), verified_email=ctx.email)

		out = _failure(result if result.get("ok") is not True else {"code": "unavailable"}, "verify")
		_audit(customer, "verify", out["code"], ctx.email, ctx.phone)
		return out


def _call_verify(provider, ctx, code):
	# Module scope: inside verify_email_otp the ``otp`` argument shadows the registry module.
	return otp.call_provider(provider.verify, ctx, code)


@frappe.whitelist()
def get_email_verification_status(customer):
	"""Local read of the verification flags (no provider call)."""
	if not frappe.has_permission("Customer", "read", customer):
		frappe.throw(_("You don't have permission to read this customer"), frappe.PermissionError)
	meta = frappe.get_meta("Customer")
	fields = [f for f in VERIFICATION_FIELDS if meta.has_field(f)]
	row = (frappe.db.get_value("Customer", customer, fields, as_dict=True) if fields else None) or {}
	return {
		"custom_email_verified": cint(row.get("custom_email_verified")),
		"custom_verified_email": row.get("custom_verified_email") or "",
		"custom_email_verified_on": str(row.get("custom_email_verified_on") or ""),
		"custom_email_verified_by": row.get("custom_email_verified_by") or "",
		"custom_email_verified_via": row.get("custom_email_verified_via") or "",
	}


def _mark_verified(customer, email, provider_name):
	frappe.db.set_value(
		"Customer",
		customer,
		{
			"custom_email_verified": 1,
			"custom_email_verified_on": now_datetime(),
			"custom_email_verified_by": frappe.session.user,
			"custom_verified_email": email,
			"custom_email_verified_via": provider_name,
		},
	)
	try:
		from pos_next.realtime_events import emit_customer_event

		emit_customer_event(frappe.get_doc("Customer", customer), "on_update")
	except Exception:
		pass


def _log_unexpected(title):
	"""Error Log entry with a fixed message only (no payload, headers or traceback)."""
	try:
		frappe.log_error(message=title, title="Customer Email OTP")
	except Exception:
		pass


# ---------------------------------------------------------------------------
# Customer doc events
# ---------------------------------------------------------------------------

def protect_email_verification_fields(doc, method=None):
	"""validate: the verified fields can only be set by this module.

	Prevents a client from forging the badge through frappe.client.set_value /
	save. Our own writes use frappe.db.set_value, which skips validate.
	"""
	if not frappe.get_meta("Customer").has_field("custom_email_verified"):
		return
	if doc.is_new():
		for field in VERIFICATION_FIELDS:
			doc.set(field, 0 if field == "custom_email_verified" else None)
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	for field in VERIFICATION_FIELDS:
		doc.set(field, before.get(field))


def reset_email_verification_on_email_change(doc, method=None):
	"""on_update: clear the verified flag when email_id differs from the verified one."""
	if doc.has_value_changed("email_id"):
		# A pending code must never survive an email change.
		from pos_next.integrations.otp_frappe_email import clear_code

		clear_code(doc.name)
	if not cint(doc.get("custom_email_verified")):
		return
	current = (doc.get("email_id") or "").strip().lower()
	verified = (doc.get("custom_verified_email") or "").strip().lower()
	if current and current == verified:
		return
	reset = {
		"custom_email_verified": 0,
		"custom_email_verified_on": None,
		"custom_email_verified_by": None,
		"custom_verified_email": None,
		"custom_email_verified_via": None,
	}
	doc.db_set(reset, update_modified=False)
	for key, value in reset.items():
		doc.set(key, value)
