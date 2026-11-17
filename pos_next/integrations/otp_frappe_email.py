"""Built-in Frappe email OTP provider.

Only a sha256 of customer, email and code is cached (never the code itself);
the code is bound to the customer and email it was sent to.

The mail is sent with redact_message_after_send so the code is wiped from the
Email Queue after a successful send; a failed send leaves an unredacted queue
row until it is retried or cleared. Callers must enforce verify-attempt limits.
"""

import hashlib
import hmac
import secrets
from types import SimpleNamespace

import frappe
from frappe import _

from pos_next import utils
from pos_next.integrations.otp import OTP_LENGTH, OTP_PROVIDER_API

_DEFAULT_TTL = 900
_LOG_TITLE = "Customer Email OTP (Frappe Email)"


def _key(customer):
	return f"pos_next:email_otp:code:{customer}"


def _hash(customer, email, code):
	return hashlib.sha256(f"{customer}|{(email or '').lower()}|{code}".encode()).hexdigest()


def clear_code(customer):
	frappe.cache().delete_value(_key(customer))


def _ttl(pos_profile):
	ttl = None
	if pos_profile:
		ttl = frappe.db.get_value("POS Settings", {"pos_profile": pos_profile}, "otp_ttl_seconds")
	try:
		ttl = int(ttl)
	except (TypeError, ValueError):
		ttl = 0
	return ttl if ttl > 0 else _DEFAULT_TTL


def _company(pos_profile):
	company = frappe.db.get_value("POS Profile", pos_profile, "company") if pos_profile else None
	return company or frappe.defaults.get_global_default("company") or frappe.local.site


def _result(ok, code, message=""):
	return {"ok": ok, "code": code, "message": message}


def _send(ctx):
	ttl = _ttl(ctx.pos_profile)
	code = f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"
	frappe.cache().set_value(_key(ctx.customer), _hash(ctx.customer, ctx.email, code), expires_in_sec=ttl)
	error = None
	try:
		frappe.sendmail(
			recipients=[ctx.email],
			subject=_("Your verification code"),
			template="customer_email_otp",
			args={
				"code": code,
				"minutes": max(ttl // 60, 1),
				"company": _company(ctx.pos_profile),
			},
			now=True,
			redact_message_after_send=True,
		)
	except Exception as e:
		error = type(e).__name__
	if error:
		# Logged outside the except block, without Sentry: neither frame locals nor
		# the request body (the code) may leave the server.
		clear_code(ctx.customer)
		utils.log_error_without_telemetry(_LOG_TITLE, f"sendmail failed: {error}")
		return _result(False, "unavailable")
	return _result(True, "sent")


def _verify(ctx, otp):
	# expires=True: a TTL key must not be memoised per process (a send in the
	# same process would otherwise be invisible to this read).
	stored = frappe.cache().get_value(_key(ctx.customer), expires=True)
	if not stored:
		return _result(False, "expired")
	if hmac.compare_digest(str(stored), _hash(ctx.customer, ctx.email, str(otp or "").strip())):
		clear_code(ctx.customer)
		return _result(True, "verified")
	return _result(False, "invalid_otp")


def _clear(ctx):
	"""Provider ``clear``: forget the pending code (email change, reset)."""
	clear_code(ctx.customer)


def _health():
	server = frappe.db.get_value(
		"Email Account", {"default_outgoing": 1, "enable_outgoing": 1}, "smtp_server"
	)
	if server or frappe.conf.get("mail_server"):
		return {"ok": True, "message": "", "fix_url": None}
	return {"ok": False, "message": _("Email sending is not configured"), "fix_url": "/app/email-account"}


def get_provider():
	return SimpleNamespace(
		name="frappe_email",
		label=_("Email (Frappe)"),
		api=OTP_PROVIDER_API,
		requires_phone=False,
		health=_health,
		send=_send,
		verify=_verify,
		clear=_clear,
	)
