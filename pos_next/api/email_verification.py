# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""
Customer email OTP verification (cashier initiated).

Sends a one-time code to the customer's email through the Magento
``email-verification/customer/otp`` REST endpoints and records the result on the
Customer (badge only, nothing is gated on it).

Design notes
------------
* Generic: pos_next never imports a client app. The Magento URL / token are read
  defensively from the single doctype "Magento Setting" (if present). Missing
  settings soft-fail with code ``not_configured``.
* The phone number is taken from ``Customer.mobile_no`` server side, never from
  the client, and normalised to ``+9647XXXXXXXXX``.
* The OTP and the Bearer token are never logged, stored in Error Log / API
  History / Comments, or returned in responses.
* Magento answers verify failures with HTTP 200 and ``{"status": false}``; the
  body ``status`` is therefore always checked.
* The feature is gated by ``POS Settings.enable_customer_email_verification``
  (default off) — except for Friends & Family members (optional POSNext
  Promotions app), who must have a verified email for F&F and can therefore
  always be verified.
"""

import json
import re
import time

import frappe
import requests
from frappe import _
from frappe.utils import cint, now_datetime

SEND_ENDPOINT = "/rest/V1/miraaya/email-verification/customer/otp/send"
VERIFY_ENDPOINT = "/rest/V1/miraaya/email-verification/customer/otp/verify"
REQUEST_TIMEOUT = (5, 20)  # (connect, read) seconds

DEFAULT_OTP_TTL = 900  # seconds
RESEND_COOLDOWN = 60  # seconds between sends per customer
MAX_SENDS_PER_HOUR = 5
MAX_VERIFY_ATTEMPTS = 10  # per issued code window
HOUR = 3600
LOCK_TIMEOUT = 30

FABRICATED_EMAIL_SUFFIX = "@pos.miraaya"
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
OTP_RE = re.compile(r"^\d{6}$")

VERIFICATION_FIELDS = (
	"custom_email_verified",
	"custom_email_verified_on",
	"custom_email_verified_by",
	"custom_verified_email",
)

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


# ---------------------------------------------------------------------------
# Messages / responses
# ---------------------------------------------------------------------------

def _messages():
	# Function (not a constant) so strings are translated at call time.
	return {
		"phone_required": _("Customer has no phone number."),
		"invalid_phone": _("Invalid Iraqi phone number."),
		"invalid_email": _("Enter a valid email address."),
		"customer_not_found": _("No Magento account was found for this customer's phone number."),
		"not_synced": _("Customer is not registered in Magento yet."),
		"sync_pending": _(
			"Customer is saved but not synced with Magento yet. Please try again in a moment."
		),
		"email_taken": _("This email belongs to another account."),
		"server_error": _("Could not send the code, please try again."),
		"unavailable": _("Magento is unreachable."),
		"expired": _("Code expired. Request a new one."),
		"invalid_otp": _("Wrong code (or email changed)."),
		"not_configured": _("Magento not configured"),
		"credentials_invalid": _("Magento credentials are invalid or lack permission."),
		"disabled": _("Email verification is disabled."),
		"email_not_saved": _("Save the customer's email before verifying it."),
		"busy": _("Another request is in progress. Please wait."),
	}


def _result(ok, code, message=None, **extra):
	out = {"ok": bool(ok), "code": code, "message": message or _messages().get(code) or code}
	out.update({k: v for k, v in extra.items() if v is not None})
	return out


def _too_many(retry_after):
	retry_after = max(1, cint(retry_after))
	return _result(
		False,
		"too_many_attempts",
		_("Too many attempts. Try again in {0}s.").format(retry_after),
		retry_after=retry_after,
	)


# ---------------------------------------------------------------------------
# Normalisation / validation helpers
# ---------------------------------------------------------------------------

def normalize_iraqi_phone(value):
	"""Normalise an Iraqi mobile number to ``+9647XXXXXXXXX`` or return None.

	Accepts ``964-7...``, ``+964...``, ``00964...``, ``07...``, ``7...`` with any
	spaces / dashes / parentheses and Arabic-Indic digits.
	"""
	if value is None:
		return None
	text = str(value).translate(_ARABIC_DIGITS)
	text = re.sub(r"[\s\-().]", "", text)
	if not text:
		return None
	if text.startswith("+"):
		digits = text[1:]
	else:
		digits = text
	if not digits.isdigit():
		return None
	if not text.startswith("+") and digits.startswith("00964"):
		digits = digits[2:]
	if digits.startswith("964"):
		national = digits[3:]
		if national.startswith("0"):  # +964 07xx...
			national = national[1:]
	elif digits.startswith("0"):
		national = digits[1:]
	else:
		national = digits
	if len(national) == 10 and national.startswith("7"):
		return "+964" + national
	return None


def is_fabricated_email(email):
	return (email or "").strip().lower().endswith(FABRICATED_EMAIL_SUFFIX)


def _clean_email(email):
	email = (email or "").strip()
	if not email or is_fabricated_email(email) or not EMAIL_RE.match(email):
		return None
	return email


def mask_phone(phone):
	phone = phone or ""
	return phone[:4] + "*" * max(0, len(phone) - 7) + phone[-3:] if len(phone) > 7 else "***"


# ---------------------------------------------------------------------------
# Feature flag / Magento configuration
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


def _get_magento_config():
	"""Return (base_url, headers) from "Magento Setting", or None if unavailable.

	Deliberately does not use masar_miraaya.api.base_data (test-mode bypass can
	fake success responses; OTP must never be faked).
	"""
	try:
		if not frappe.db.exists("DocType", "Magento Setting"):
			return None
		values = frappe.db.get_singles_dict("Magento Setting") or {}
	except Exception:
		return None
	url = str(values.get("magento_url") or "").strip().rstrip("/")
	use_prod = cint(values.get("token"))
	auth = values.get("magento_admin_prod_auth") if use_prod else values.get("magento_auth")
	auth = str(auth or "").strip()
	if not url or not auth:
		return None
	return url, {"Authorization": f"Bearer {auth}", "Content-Type": "application/json"}


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


def _save_state(customer, state):
	_cache().set_value(_state_key(customer), json.dumps(state), expires_in_sec=HOUR + 60)


def _send_gate(state, now):
	"""Return retry_after seconds if sending is blocked, else 0."""
	sends = [t for t in state["sends"] if now - t < HOUR]
	state["sends"] = sends
	if sends:
		wait = RESEND_COOLDOWN - (now - max(sends))
		if wait > 0:
			return int(wait) + 1
	if len(sends) >= MAX_SENDS_PER_HOUR:
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
# Magento HTTP
# ---------------------------------------------------------------------------

def _post(path, payload):
	"""POST to Magento. Returns (http_status, body) or (None, None) when unreachable.

	Never logs payload / headers (they carry the OTP and the Bearer token).
	Configuration problems are checked by the caller before this is reached.
	"""
	config = _get_magento_config()
	if not config:
		return "not_configured", None
	base_url, headers = config
	try:
		resp = requests.post(base_url + path, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
	except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
		return None, None
	except requests.exceptions.RequestException:
		return None, None
	try:
		body = resp.json()
	except ValueError:
		body = None
	if isinstance(body, list) and body:
		body = body[0]
	if not isinstance(body, dict):
		body = {}
	return resp.status_code, body


_ERROR_SUBSTRINGS = (
	("phone is required", "phone_required"),
	("invalid phone", "invalid_phone"),
	("valid email", "invalid_email"),
	("no customer", "customer_not_found"),
	("already registered", "email_taken"),
	("another account", "email_taken"),
	("unable to store", "server_error"),
	("expired", "expired"),
	("invalid verification code", "invalid_otp"),
	("invalid code", "invalid_otp"),
)


def _map_message(message):
	text = (message or "").lower()
	for needle, code in _ERROR_SUBSTRINGS:
		if needle in text:
			return code
	return None


def _safe_message(message):
	return (str(message or "").strip())[:200]


def _error_from(http_status, body, default_code):
	"""Map a Magento error (HTTP >=400, or 200 with status:false) to a result."""
	raw = body.get("message") if isinstance(body, dict) else None
	code = _map_message(raw)
	if code:
		return _result(False, code)
	if http_status in (401, 403):
		return _result(False, "credentials_invalid")
	if http_status and http_status >= 500:
		return _result(False, "server_error")
	return _result(False, default_code, _safe_message(raw) or None)


# ---------------------------------------------------------------------------
# Common checks
# ---------------------------------------------------------------------------

def _prepare(customer, email, pos_profile):
	"""Run checks common to send/verify. Returns (ctx, error_result)."""
	if not customer:
		frappe.throw(_("Customer is required"))
	if not is_verification_allowed(customer, pos_profile):
		return None, _result(False, "disabled")
	if not frappe.has_permission("Customer", "write", customer):
		frappe.throw(_("You don't have permission to verify this customer's email"), frappe.PermissionError)

	meta = frappe.get_meta("Customer")
	fields = ["name", "mobile_no", "email_id"]
	has_magento_id = meta.has_field("custom_customer_id")
	if has_magento_id:
		fields.append("custom_customer_id")
	doc = frappe.db.get_value("Customer", customer, fields, as_dict=True)
	if not doc:
		frappe.throw(_("Customer {0} not found").format(customer), frappe.DoesNotExistError)

	# Magento identifies the customer by phone, not by the local Magento id. A customer
	# just created in the POS may lack custom_customer_id (registration failed, was
	# skipped, or Magento answered "already exists" without an id), so do not block
	# here: let Magento decide and translate "no customer" into ``sync_pending``.
	synced = bool(has_magento_id and doc.get("custom_customer_id"))

	saved_email = (doc.get("email_id") or "").strip()
	if _clean_email(saved_email) is None:
		return None, _result(False, "invalid_email")
	if email and (email or "").strip().lower() != saved_email.lower():
		return None, _result(False, "email_not_saved")

	phone_raw = (doc.get("mobile_no") or "").strip()
	if not phone_raw:
		return None, _result(False, "phone_required")
	phone = normalize_iraqi_phone(phone_raw)
	if not phone:
		return None, _result(False, "invalid_phone")

	if not _get_magento_config():
		return None, _result(False, "not_configured")

	return {"customer": customer, "email": saved_email, "phone": phone, "synced": synced}, None


def _unsynced_aware(ctx, result):
	"""Magento has no customer for this phone and we hold no Magento id: sync is pending."""
	if result.get("code") == "customer_not_found" and not ctx.get("synced"):
		return _result(False, "sync_pending")
	return result


def _audit(customer, action, code, email, phone, http_status=None):
	"""Customer comment audit trail. Never contains the OTP or the token."""
	try:
		text = (
			f"Email verification {action}: {code} | email={email} | phone={mask_phone(phone)} "
			f"| by={frappe.session.user}"
		)
		if http_status:
			text += f" | http={http_status}"
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
	ctx, err = _prepare(customer, email, pos_profile)
	if err:
		return err

	with _Lock(customer) as lock:
		if not lock.acquired:
			return _result(False, "busy")

		now = time.time()
		state = _load_state(customer)
		retry_after = _send_gate(state, now)
		if retry_after:
			return _too_many(retry_after)

		http_status, body = _post(SEND_ENDPOINT, {"phone": ctx["phone"], "email": ctx["email"]})

		if http_status == "not_configured":
			return _result(False, "not_configured")

		if http_status is None:
			# Request may or may not have reached Magento: count it, keep cooldown.
			state["sends"].append(now)
			_save_state(customer, state)
			_audit(customer, "send", "unavailable", ctx["email"], ctx["phone"])
			return _result(False, "unavailable")

		if http_status >= 400:
			if http_status >= 500:
				state["sends"].append(now)
				_save_state(customer, state)
			result = _unsynced_aware(ctx, _error_from(http_status, body, "send_failed"))
			_audit(customer, "send", result["code"], ctx["email"], ctx["phone"], http_status)
			if result["code"] in ("credentials_invalid", "server_error", "send_failed"):
				_log_unexpected(f"Email OTP send failed (HTTP {http_status})")
			return result

		if body.get("success") is False or body.get("status") is False:
			result = _unsynced_aware(ctx, _error_from(http_status, body, "send_failed"))
			_audit(customer, "send", result["code"], ctx["email"], ctx["phone"], http_status)
			return result

		if body.get("otp_required") is False:
			_audit(customer, "send", "otp_not_required", ctx["email"], ctx["phone"], http_status)
			return _result(
				True,
				"otp_not_required",
				_("No verification code is needed for this email."),
				otp_required=False,
			)

		state["sends"].append(now)
		state["attempts"] = 0
		state["attempts_reset_at"] = now
		_save_state(customer, state)
		_audit(customer, "send", "sent", ctx["email"], ctx["phone"], http_status)

		expires_in = cint(body.get("expires_in")) or DEFAULT_OTP_TTL
		resend_in = max(cint(body.get("resend_in")), RESEND_COOLDOWN)
		return _result(True, "sent", _("Verification code sent."), expires_in=expires_in, resend_in=resend_in)


@frappe.whitelist(methods=["POST"])
def verify_email_otp(customer, otp, email=None, pos_profile=None):
	"""Verify the 6-digit code. Success is decided by the response body ``status``."""
	ctx, err = _prepare(customer, email, pos_profile)
	if err:
		return err

	otp = str(otp or "").translate(_ARABIC_DIGITS).strip()
	if not OTP_RE.match(otp):
		return _result(False, "invalid_otp")

	with _Lock(customer) as lock:
		if not lock.acquired:
			return _result(False, "busy")

		now = time.time()
		state = _load_state(customer)
		if state["attempts"] >= MAX_VERIFY_ATTEMPTS:
			remaining = DEFAULT_OTP_TTL - (now - state["attempts_reset_at"])
			return _too_many(max(remaining, RESEND_COOLDOWN))
		state["attempts"] += 1
		_save_state(customer, state)

		http_status, body = _post(
			VERIFY_ENDPOINT, {"phone": ctx["phone"], "email": ctx["email"], "otp": otp}
		)

		if http_status == "not_configured":
			return _result(False, "not_configured")
		if http_status is None:
			_audit(customer, "verify", "unavailable", ctx["email"], ctx["phone"])
			return _result(False, "unavailable")

		# HTTP 200 does NOT mean success: Magento reports failures in body.status.
		if http_status == 200 and body.get("status") is True:
			_mark_verified(customer, ctx["email"])
			state["attempts"] = 0
			_save_state(customer, state)
			_audit(customer, "verify", "verified", ctx["email"], ctx["phone"], http_status)
			return _result(
				True,
				"verified",
				_("Email verified"),
				verified_email=ctx["email"],
			)

		result = _unsynced_aware(ctx, _error_from(http_status, body, "verify_failed"))
		if result["code"] in ("credentials_invalid", "server_error"):
			_log_unexpected(f"Email OTP verify failed (HTTP {http_status})")
		_audit(customer, "verify", result["code"], ctx["email"], ctx["phone"], http_status)
		return result


@frappe.whitelist()
def get_email_verification_status(customer):
	"""Local read of the verification flags (no Magento call)."""
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
	}


def _mark_verified(customer, email):
	frappe.db.set_value(
		"Customer",
		customer,
		{
			"custom_email_verified": 1,
			"custom_email_verified_on": now_datetime(),
			"custom_email_verified_by": frappe.session.user,
			"custom_verified_email": email,
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
	}
	doc.db_set(reset, update_modified=False)
	for key, value in reset.items():
		doc.set(key, value)
