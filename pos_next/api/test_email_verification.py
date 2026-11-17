# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Unit tests for the provider-agnostic customer email OTP flow.

The active provider, settings and cache are mocked; provider-specific cases
live with each provider's own tests.
"""

import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from pos_next.api import email_verification as ev
from pos_next.integrations.otp import OTP_PROVIDER_API

OTP = "482913"
MODULE = "pos_next.api.email_verification"
ORIGINAL_AUDIT = ev._audit
ORIGINAL_MARK_VERIFIED = ev._mark_verified


class FakeCache:
	def __init__(self):
		self.store = {}

	def get_value(self, key, *a, **k):
		return self.store.get(key)

	def set_value(self, key, val, *a, **k):
		self.store[key] = val

	def lock(self, name, timeout=None):
		lock = MagicMock()
		lock.acquire.return_value = True
		return lock


def fake_provider(name="fake", requires_phone=False, send=None, verify=None, health=None):
	return SimpleNamespace(
		name=name,
		label=name,
		api=OTP_PROVIDER_API,
		requires_phone=requires_phone,
		health=MagicMock(return_value=health or {"ok": True, "message": "", "fix_url": None}),
		send=MagicMock(return_value=send or {"ok": True, "code": "sent", "message": ""}),
		verify=MagicMock(return_value=verify or {"ok": True, "code": "verified", "message": ""}),
	)


CUSTOMER_ROW = frappe._dict(
	name="CUST-1",
	mobile_no="",
	email_id="jane@example.com",
)


class EmailOTPTestBase(unittest.TestCase):
	def setUp(self):
		self.cache = FakeCache()
		self.row = frappe._dict(CUSTOMER_ROW)
		self.settings = {}
		self.countries = {"United Kingdom": "gb", "Iraq": "iq"}
		self.provider = fake_provider()
		meta = MagicMock()
		meta.has_field.return_value = True
		self.patches = [
			patch(f"{MODULE}._cache", return_value=self.cache),
			patch(f"{MODULE}.is_feature_enabled", return_value=True),
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_meta", return_value=meta),
			patch(f"{MODULE}.frappe.db.get_value", side_effect=self._get_value),
			patch("pos_next.integrations.otp.get_active_provider", side_effect=lambda p: self.provider),
			patch(f"{MODULE}._audit"),
			patch(f"{MODULE}._mark_verified"),
			patch(f"{MODULE}.frappe.log_error"),
			patch("pos_next.integrations.otp.frappe.log_error"),
			patch(f"{MODULE}._is_ff_member", return_value=False),
		]
		mocks = [p.start() for p in self.patches]
		self.mock_audit = mocks[6]
		self.mock_mark = mocks[7]
		self.mock_log_error = mocks[8]
		self.addCleanup(lambda: [p.stop() for p in self.patches])

	def _get_value(self, doctype, name=None, fields=None, *a, **k):
		if doctype == "Customer":
			return self.row
		if doctype == "POS Settings":
			return frappe._dict(self.settings)
		if doctype == "Country":
			return self.countries.get(name)
		return None


class TestHelpers(unittest.TestCase):
	def test_normalize_phone(self):
		with patch(f"{MODULE}.frappe.db.get_value", side_effect=lambda dt, name, f: {"Iraq": "iq", "United Kingdom": "gb"}.get(name)):
			cases = [
				("+44 20 7946 0958", None, "+442079460958"),
				("020 7946 0958", "United Kingdom", "+442079460958"),
				("07701234567", "Iraq", "+9647701234567"),
				("٠٧٧٠١٢٣٤٥٦٧", "Iraq", "+9647701234567"),
				("0770 123 4567", None, None),  # no country, no +
				("12345", "United Kingdom", None),
				("not a phone", "United Kingdom", None),
				("", "United Kingdom", None),
				(None, "Iraq", None),
			]
			for raw, country, expected in cases:
				with self.subTest(raw=raw, country=country):
					self.assertEqual(ev.normalize_phone(raw, country), expected)

	def test_is_placeholder_email(self):
		with patch(f"{MODULE}._otp_settings", return_value=ev._OtpSettings(placeholder_email_domain="pos.example")):
			self.assertTrue(ev.is_placeholder_email("x@pos.example", "P"))
			self.assertTrue(ev.is_placeholder_email("X@POS.EXAMPLE", "P"))
			self.assertFalse(ev.is_placeholder_email("x@sub.pos.example.com", "P"))
			self.assertFalse(ev.is_placeholder_email("x@example.com", "P"))
		with patch(f"{MODULE}._otp_settings", return_value=ev._OtpSettings()):
			self.assertFalse(ev.is_placeholder_email("x@pos.example", "P"))

	def test_settings_defaults_for_blank_values(self):
		row = frappe._dict(
			otp_ttl_seconds=None,
			otp_resend_cooldown=0,
			otp_max_sends_per_hour="",
			default_phone_country=None,
			placeholder_email_domain=None,
		)
		with patch(f"{MODULE}.frappe.db.get_value", return_value=row) as gv:
			s = ev._otp_settings("P")
		self.assertEqual(gv.call_args.args[1], {"pos_profile": "P", "enabled": 1})
		self.assertEqual((s.otp_ttl_seconds, s.otp_resend_cooldown, s.otp_max_sends_per_hour), (900, 60, 5))
		with patch(f"{MODULE}.frappe.db.get_value", return_value=None):
			s = ev._otp_settings("P")
		self.assertEqual(s.otp_ttl_seconds, 900)
		s = ev._otp_settings(None)
		self.assertEqual(s.otp_resend_cooldown, 60)


class TestSend(EmailOTPTestBase):
	def test_uses_active_provider(self):
		with patch("pos_next.integrations.otp.get_active_provider", return_value=self.provider) as gap:
			res = ev.send_email_otp("CUST-1", pos_profile="P1")
		gap.assert_called_with("P1")
		self.assertTrue(res["ok"])
		self.assertEqual(res["code"], "sent")
		self.provider.send.assert_called_once()
		ctx = self.provider.send.call_args.args[0]
		self.assertEqual((ctx.customer, ctx.email, ctx.phone, ctx.pos_profile), ("CUST-1", "jane@example.com", None, "P1"))
		self.assertEqual(res["expires_in"], 900)
		self.assertEqual(res["resend_in"], 60)

	def test_not_configured_when_no_provider(self):
		self.provider.health.return_value = {"ok": False, "message": "SMTP missing", "fix_url": "/app/email-account"}
		res = ev.send_email_otp("CUST-1")
		self.assertFalse(res["ok"])
		self.assertEqual(res["code"], "not_configured")
		self.provider.send.assert_not_called()
		self.provider = None
		res = ev.send_email_otp("CUST-1")
		self.assertEqual((res["ok"], res["code"]), (False, "not_configured"))

	def test_not_configured_uses_generic_text(self):
		self.provider.health.return_value = {"ok": False, "message": "Provider secret XYZ broken", "fix_url": None}
		res = ev.send_email_otp("CUST-1")
		self.assertEqual(res["message"], "Email verification is not set up. Ask an administrator.")
		self.assertNotIn("XYZ", json.dumps(res))
		# Provider-returned not_configured on send uses the same generic text.
		self.provider.health.return_value = {"ok": True, "message": "", "fix_url": None}
		self.provider.send.return_value = {"ok": False, "code": "not_configured", "message": "token XYZ missing"}
		res = ev.send_email_otp("CUST-1")
		self.assertEqual(res["code"], "not_configured")
		self.assertEqual(res["message"], "Email verification is not set up. Ask an administrator.")

	def test_unavailable_uses_generic_text(self):
		self.provider.send.return_value = {"ok": False, "code": "unavailable", "message": "stack trace at host 10.0.0.1"}
		res = ev.send_email_otp("CUST-1")
		self.assertEqual(res["code"], "unavailable")
		self.assertEqual(res["message"], "Could not send the code, please try again.")
		self.provider.send.side_effect = RuntimeError("boom 10.0.0.1")
		self.cache.store.clear()
		res = ev.send_email_otp("CUST-1")
		self.assertEqual(res["code"], "unavailable")
		self.assertNotIn("10.0.0.1", json.dumps(res))

	def test_malformed_or_inconsistent_send_result_is_unavailable(self):
		for bad in (None, {"code": "sent"}, {"ok": True, "code": "bogus"}, {"ok": True, "code": "verified"}, {"ok": False, "code": "sent"}):
			with self.subTest(bad=bad):
				self.cache.store.clear()
				self.provider.send.return_value = bad
				res = ev.send_email_otp("CUST-1")
				self.assertFalse(res["ok"])
				self.assertEqual(res["code"], "unavailable")

	def test_rejected_passes_provider_message(self):
		self.provider.send.return_value = {"ok": False, "code": "rejected", "message": "already registered"}
		res = ev.send_email_otp("CUST-1")
		self.assertEqual((res["ok"], res["code"], res["message"]), (False, "rejected", "already registered"))
		self.cache.store.clear()
		self.provider.send.return_value = {"ok": False, "code": "rejected", "message": ""}
		res = ev.send_email_otp("CUST-1")
		self.assertEqual(res["code"], "rejected")
		self.assertTrue(res["message"])
		self.cache.store.clear()
		self.provider.send.return_value = {"ok": False, "code": "rejected", "message": "x" * 500}
		self.assertLessEqual(len(ev.send_email_otp("CUST-1")["message"]), 200)

	def test_provider_rate_limited_passes_retry_after(self):
		self.provider.send.return_value = {"ok": False, "code": "rate_limited", "message": "slow down", "retry_after": 42}
		res = ev.send_email_otp("CUST-1")
		self.assertEqual((res["code"], res["retry_after"]), ("rate_limited", 42))
		self.assertNotEqual(res["message"], "slow down")

	def test_otp_not_required_does_not_mark_verified(self):
		self.provider.send.return_value = {"ok": True, "code": "otp_not_required", "message": ""}
		res = ev.send_email_otp("CUST-1")
		self.assertTrue(res["ok"])
		self.assertEqual(res["code"], "otp_not_required")
		self.mock_mark.assert_not_called()

	def test_double_send_single_email(self):
		first = ev.send_email_otp("CUST-1")
		second = ev.send_email_otp("CUST-1")
		self.assertEqual(first["code"], "sent")
		self.assertEqual(second["code"], "rate_limited")
		self.assertFalse(second["ok"])
		self.assertGreater(second["retry_after"], 0)
		self.assertEqual(self.provider.send.call_count, 1)

	def test_failed_send_still_counts_for_cooldown(self):
		self.provider.send.return_value = {"ok": False, "code": "rejected", "message": "no"}
		ev.send_email_otp("CUST-1")
		self.assertEqual(ev.send_email_otp("CUST-1")["code"], "rate_limited")
		self.assertEqual(self.provider.send.call_count, 1)

	def test_hourly_cap(self):
		now = time.time()
		state = ev._load_state("CUST-1")
		state["sends"] = [now - 3000, now - 2500, now - 2000, now - 1500, now - 200]
		ev._save_state("CUST-1", state)
		res = ev.send_email_otp("CUST-1")
		self.assertEqual(res["code"], "rate_limited")
		self.assertGreater(res["retry_after"], 60)
		self.provider.send.assert_not_called()

	def test_limits_from_profile(self):
		self.settings = {"otp_resend_cooldown": 5, "otp_ttl_seconds": 300, "otp_max_sends_per_hour": 2}
		t0 = 1_000_000.0
		with patch(f"{MODULE}.time.time", return_value=t0):
			res = ev.send_email_otp("CUST-1", pos_profile="P1")
			self.assertEqual((res["expires_in"], res["resend_in"]), (300, 5))
			self.assertEqual(ev.send_email_otp("CUST-1", pos_profile="P1")["code"], "rate_limited")
		with patch(f"{MODULE}.time.time", return_value=t0 + 6):
			self.assertEqual(ev.send_email_otp("CUST-1", pos_profile="P1")["code"], "sent")
		with patch(f"{MODULE}.time.time", return_value=t0 + 20):
			res = ev.send_email_otp("CUST-1", pos_profile="P1")
		self.assertEqual(res["code"], "rate_limited")  # hourly cap of 2
		self.assertEqual(self.provider.send.call_count, 2)

	def test_non_iraqi_phone_accepted(self):
		self.settings = {"default_phone_country": "United Kingdom"}
		self.provider = fake_provider(requires_phone=True)
		self.row.mobile_no = "+44 20 7946 0958"
		res = ev.send_email_otp("CUST-1", pos_profile="P1")
		self.assertEqual(res["code"], "sent")
		self.assertEqual(self.provider.send.call_args.args[0].phone, "+442079460958")
		# National format resolved through the profile's country.
		self.cache.store.clear()
		self.row.mobile_no = "020 7946 0958"
		ev.send_email_otp("CUST-1", pos_profile="P1")
		self.assertEqual(self.provider.send.call_args.args[0].phone, "+442079460958")

	def test_phone_errors_when_provider_requires_phone(self):
		self.provider = fake_provider(requires_phone=True)
		self.row.mobile_no = ""
		self.assertEqual(ev.send_email_otp("CUST-1")["code"], "phone_required")
		self.row.mobile_no = "12345"
		self.assertEqual(ev.send_email_otp("CUST-1")["code"], "invalid_phone")
		self.provider.send.assert_not_called()

	def test_phone_not_required_for_email_provider(self):
		self.provider = fake_provider(name="frappe_email", requires_phone=False)
		self.row.mobile_no = ""
		res = ev.send_email_otp("CUST-1")
		self.assertEqual(res["code"], "sent")
		self.assertIsNone(self.provider.send.call_args.args[0].phone)
		self.row.mobile_no = "garbage"
		self.cache.store.clear()
		self.assertEqual(ev.send_email_otp("CUST-1")["code"], "sent")

	def test_placeholder_email_rejected(self):
		self.settings = {"placeholder_email_domain": "pos.example"}
		self.row.email_id = "x@pos.example"
		res = ev.send_email_otp("CUST-1", pos_profile="P1")
		self.assertEqual(res["code"], "invalid_email")
		self.provider.send.assert_not_called()

	def test_blank_and_invalid_email_rejected(self):
		for email in ("", "not-an-email"):
			with self.subTest(email=email):
				self.row.email_id = email
				self.assertEqual(ev.send_email_otp("CUST-1")["code"], "invalid_email")
		self.provider.send.assert_not_called()

	def test_email_param_must_match_saved(self):
		self.assertEqual(ev.send_email_otp("CUST-1", "other@example.com")["code"], "email_not_saved")
		self.assertEqual(ev.send_email_otp("CUST-1", "JANE@example.com")["code"], "sent")

	def test_flag_off(self):
		with patch(f"{MODULE}.is_feature_enabled", return_value=False):
			self.assertEqual(ev.send_email_otp("CUST-1")["code"], "disabled")
		self.provider.send.assert_not_called()

	def test_flag_off_but_friends_and_family_member(self):
		with (
			patch(f"{MODULE}.is_feature_enabled", return_value=False),
			patch(f"{MODULE}._is_ff_member", return_value=True),
		):
			self.assertEqual(ev.send_email_otp("CUST-1")["code"], "sent")

	def test_permission_denied(self):
		with patch(f"{MODULE}.frappe.has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				ev.send_email_otp("CUST-1")
		self.provider.send.assert_not_called()

	def test_lock_busy(self):
		lock = MagicMock()
		lock.acquire.return_value = False
		self.cache.lock = lambda *a, **k: lock
		self.assertEqual(ev.send_email_otp("CUST-1")["code"], "busy")
		self.provider.send.assert_not_called()


class TestVerify(EmailOTPTestBase):
	def test_success_marks_verified_with_provider(self):
		self.provider = fake_provider(name="frappe_email")
		res = ev.verify_email_otp("CUST-1", OTP, "jane@example.com", "P1")
		self.assertEqual((res["ok"], res["code"], res["verified_email"]), (True, "verified", "jane@example.com"))
		ctx, otp = self.provider.verify.call_args.args
		self.assertEqual((ctx.customer, ctx.email, ctx.pos_profile, otp), ("CUST-1", "jane@example.com", "P1", OTP))
		self.mock_mark.assert_called_once_with("CUST-1", "jane@example.com", "frappe_email")

	def test_mark_verified_records_provider(self):
		with (
			patch(f"{MODULE}.frappe.db.set_value") as set_value,
			patch(f"{MODULE}.frappe.get_doc"),
			patch("pos_next.realtime_events.emit_customer_event"),
		):
			ORIGINAL_MARK_VERIFIED("CUST-1", "jane@example.com", "frappe_email")
		values = set_value.call_args.args[2]
		self.assertEqual(values["custom_email_verified_via"], "frappe_email")
		self.assertEqual(values["custom_email_verified"], 1)
		self.assertEqual(values["custom_verified_email"], "jane@example.com")

	def test_only_ok_and_verified_is_success(self):
		for bad in (
			{"ok": False, "code": "verified", "message": ""},
			{"ok": True, "code": "invalid_otp", "message": ""},
			{"ok": True, "code": "sent", "message": ""},
			{"ok": "yes", "code": "verified", "message": ""},
			None,
			{"code": "verified"},
		):
			with self.subTest(bad=bad):
				self.cache.store.clear()
				self.provider.verify.return_value = bad
				res = ev.verify_email_otp("CUST-1", OTP)
				self.assertFalse(res["ok"])
		self.mock_mark.assert_not_called()

	def test_failure_codes(self):
		for code in ("invalid_otp", "expired", "unavailable", "not_configured"):
			with self.subTest(code=code):
				self.cache.store.clear()
				self.provider.verify.return_value = {"ok": False, "code": code, "message": "PROVIDER TEXT"}
				res = ev.verify_email_otp("CUST-1", OTP)
				self.assertEqual(res["code"], code)
				self.assertNotEqual(res["message"], "PROVIDER TEXT")
		self.mock_mark.assert_not_called()

	def test_bad_otp_format_no_provider_call(self):
		for bad in ("12345", "abcdef", "1234567", ""):
			with self.subTest(otp=bad):
				self.assertEqual(ev.verify_email_otp("CUST-1", bad)["code"], "invalid_otp")
		self.provider.verify.assert_not_called()

	def test_arabic_digit_otp_normalized(self):
		ev.verify_email_otp("CUST-1", "٤٨٢٩١٣")
		self.assertEqual(self.provider.verify.call_args.args[1], OTP)

	def test_ten_wrong_attempts_rate_limited(self):
		self.provider.verify.return_value = {"ok": False, "code": "invalid_otp", "message": ""}
		ev.send_email_otp("CUST-1")
		for _i in range(ev.MAX_VERIFY_ATTEMPTS):
			self.assertEqual(ev.verify_email_otp("CUST-1", OTP)["code"], "invalid_otp")
		res = ev.verify_email_otp("CUST-1", OTP)
		self.assertEqual(res["code"], "rate_limited")
		self.assertGreater(res["retry_after"], 0)
		self.assertEqual(self.provider.verify.call_count, ev.MAX_VERIFY_ATTEMPTS)
		self.assertEqual(ev.MAX_VERIFY_ATTEMPTS, 10)
		# Even a correct code is refused once locked out.
		self.provider.verify.return_value = {"ok": True, "code": "verified", "message": ""}
		self.assertEqual(ev.verify_email_otp("CUST-1", OTP)["code"], "rate_limited")
		self.mock_mark.assert_not_called()

	def test_lockout_window_uses_profile_ttl(self):
		self.settings = {"otp_ttl_seconds": 300, "otp_resend_cooldown": 30}
		self.provider.verify.return_value = {"ok": False, "code": "invalid_otp", "message": ""}
		t0 = 2_000_000.0
		with patch(f"{MODULE}.time.time", return_value=t0):
			ev.send_email_otp("CUST-1", pos_profile="P1")
			for _i in range(ev.MAX_VERIFY_ATTEMPTS):
				ev.verify_email_otp("CUST-1", OTP, pos_profile="P1")
		with patch(f"{MODULE}.time.time", return_value=t0 + 100):
			res = ev.verify_email_otp("CUST-1", OTP, pos_profile="P1")
		self.assertEqual(res["code"], "rate_limited")
		self.assertEqual(res["retry_after"], 200)

	def test_profile_access_required(self):
		perms = {"Customer": True, "POS Profile": False}
		with (
			patch(f"{MODULE}.frappe.has_permission", side_effect=lambda dt, *a, **k: perms[dt]),
			patch("pos_next.utils.frappe.db.exists", return_value=None),
		):
			with self.assertRaises(frappe.PermissionError):
				ev.send_email_otp("CUST-1", pos_profile="OTHER")
			with self.assertRaises(frappe.PermissionError):
				ev.verify_email_otp("CUST-1", OTP, pos_profile="OTHER")
		self.provider.send.assert_not_called()
		self.provider.verify.assert_not_called()
		# Assigned users pass.
		with (
			patch(f"{MODULE}.frappe.has_permission", side_effect=lambda dt, *a, **k: perms[dt]),
			patch("pos_next.utils.frappe.db.exists", return_value="row"),
		):
			self.assertEqual(ev.send_email_otp("CUST-1", pos_profile="MINE")["code"], "sent")

	def test_short_ttl_profile_cannot_reset_attempts_of_long_code(self):
		self.provider.verify.return_value = {"ok": False, "code": "invalid_otp", "message": ""}
		saved = {}
		real_set = self.cache.set_value

		def set_value(key, val, *a, **k):
			saved.update(k)
			real_set(key, val)

		self.cache.set_value = set_value
		t0 = 3_000_000.0
		self.settings = {"otp_ttl_seconds": 7200}
		with patch(f"{MODULE}.time.time", return_value=t0):
			ev.send_email_otp("CUST-1", pos_profile="LONG")
		self.settings = {"otp_ttl_seconds": 120}
		with patch(f"{MODULE}.time.time", return_value=t0 + 10):
			for _i in range(ev.MAX_VERIFY_ATTEMPTS):
				ev.verify_email_otp("CUST-1", OTP, pos_profile="SHORT")
		self.assertGreaterEqual(saved["expires_in_sec"], 7200)
		# Long after the short TTL, while the long code still lives: still locked out.
		with patch(f"{MODULE}.time.time", return_value=t0 + 5000):
			res = ev.verify_email_otp("CUST-1", OTP, pos_profile="SHORT")
		self.assertEqual(res["code"], "rate_limited")
		self.assertEqual(res["retry_after"], 2200)
		self.assertEqual(self.provider.verify.call_count, ev.MAX_VERIFY_ATTEMPTS)

	def test_lockout_after_code_ttl_is_expired(self):
		self.settings = {"otp_ttl_seconds": 300}
		self.provider.verify.return_value = {"ok": False, "code": "invalid_otp", "message": ""}
		t0 = 4_000_000.0
		with patch(f"{MODULE}.time.time", return_value=t0):
			ev.send_email_otp("CUST-1", pos_profile="P1")
			for _i in range(ev.MAX_VERIFY_ATTEMPTS):
				ev.verify_email_otp("CUST-1", OTP, pos_profile="P1")
		with patch(f"{MODULE}.time.time", return_value=t0 + 301):
			res = ev.verify_email_otp("CUST-1", OTP, pos_profile="P1")
		self.assertEqual(res["code"], "expired")
		self.assertFalse(res["ok"])
		self.assertEqual(self.provider.verify.call_count, ev.MAX_VERIFY_ATTEMPTS)

	def test_state_outlives_long_ttl(self):
		saved = {}
		self.cache.set_value = lambda key, val, *a, **k: saved.update(k)
		ev._save_state("CUST-1", ev._load_state("CUST-1"), ttl=7200)
		self.assertGreaterEqual(saved["expires_in_sec"], 7200)

	def test_new_send_resets_attempts(self):
		self.provider.verify.return_value = {"ok": False, "code": "invalid_otp", "message": ""}
		for _i in range(3):
			ev.verify_email_otp("CUST-1", OTP)
		self.assertEqual(ev._load_state("CUST-1")["attempts"], 3)
		ev.send_email_otp("CUST-1")
		self.assertEqual(ev._load_state("CUST-1")["attempts"], 0)

	def test_failed_send_does_not_reset_attempts(self):
		self.provider.verify.return_value = {"ok": False, "code": "invalid_otp", "message": ""}
		for _i in range(3):
			ev.verify_email_otp("CUST-1", OTP)
		self.provider.send.return_value = {"ok": False, "code": "unavailable", "message": ""}
		ev.send_email_otp("CUST-1")
		self.assertEqual(ev._load_state("CUST-1")["attempts"], 3)

	def test_flag_off_and_permission(self):
		with patch(f"{MODULE}.is_feature_enabled", return_value=False):
			self.assertEqual(ev.verify_email_otp("CUST-1", OTP)["code"], "disabled")
		with patch(f"{MODULE}.frappe.has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				ev.verify_email_otp("CUST-1", OTP)
		self.provider.verify.assert_not_called()


class TestSecrets(EmailOTPTestBase):
	def test_otp_never_logged_or_stored(self):
		results = []
		for verify in (
			{"ok": False, "code": "invalid_otp", "message": ""},
			{"ok": True, "code": "verified", "message": ""},
			{"ok": False, "code": "unavailable", "message": ""},
		):
			self.provider.verify.return_value = verify
			results.append(ev.verify_email_otp("CUST-1", OTP))
		self.provider.verify.side_effect = RuntimeError("boom")
		results.append(ev.verify_email_otp("CUST-1", OTP))
		text = "\n".join(
			[json.dumps(results, default=str)]
			+ [str(c) for c in self.mock_audit.call_args_list]
			+ [str(c) for c in self.mock_log_error.call_args_list]
			+ [json.dumps(self.cache.store, default=str)]
		)
		self.assertNotIn(OTP, text)

	def test_audit_text_has_no_otp(self):
		doc = MagicMock()
		with patch(f"{MODULE}.frappe.get_doc", return_value=doc):
			ORIGINAL_AUDIT("CUST-1", "verify", "invalid_otp", "jane@example.com", "+9647701234567")
		text = doc.add_comment.call_args.args[1]
		self.assertNotIn(OTP, text)
		self.assertNotIn("+9647701234567", text)  # phone is masked
		self.assertIn("invalid_otp", text)


class TestStatus(unittest.TestCase):
	def test_status_includes_provider(self):
		meta = MagicMock()
		meta.has_field.return_value = True
		row = frappe._dict(custom_email_verified=1, custom_verified_email="a@x.com", custom_email_verified_via="frappe_email")
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_meta", return_value=meta),
			patch(f"{MODULE}.frappe.db.get_value", return_value=row),
		):
			res = ev.get_email_verification_status("CUST-1")
		self.assertEqual(res["custom_email_verified_via"], "frappe_email")
		self.assertEqual(res["custom_email_verified"], 1)


class TestDocEvents(unittest.TestCase):
	def _doc(self, **values):
		doc = MagicMock()
		store = dict(values)
		doc.get.side_effect = lambda k, d=None: store.get(k, d)
		doc.set.side_effect = lambda k, v: store.__setitem__(k, v)
		doc.has_value_changed.return_value = False
		doc._store = store
		return doc

	def test_reset_on_email_change(self):
		doc = self._doc(
			custom_email_verified=1,
			custom_verified_email="a@x.com",
			custom_email_verified_via="frappe_email",
			email_id="b@x.com",
		)
		ev.reset_email_verification_on_email_change(doc)
		doc.db_set.assert_called_once()
		reset = doc.db_set.call_args.args[0]
		self.assertEqual(reset["custom_email_verified"], 0)
		self.assertIsNone(reset["custom_email_verified_via"])
		self.assertEqual(doc._store["custom_email_verified"], 0)
		self.assertIsNone(doc._store["custom_email_verified_via"])

	def test_no_reset_when_same_email_case_insensitive(self):
		doc = self._doc(custom_email_verified=1, custom_verified_email="a@x.com", email_id="A@X.com")
		ev.reset_email_verification_on_email_change(doc)
		doc.db_set.assert_not_called()

	def test_no_reset_when_not_verified(self):
		doc = self._doc(custom_email_verified=0, email_id="b@x.com")
		ev.reset_email_verification_on_email_change(doc)
		doc.db_set.assert_not_called()

	def test_protect_fields_reverts_client_changes(self):
		meta = MagicMock()
		meta.has_field.return_value = True
		doc = self._doc(custom_email_verified=1, custom_email_verified_via="forged")
		doc.is_new.return_value = False
		doc.get_doc_before_save.return_value = frappe._dict(custom_email_verified=0, custom_email_verified_via=None)
		with patch(f"{MODULE}.frappe.get_meta", return_value=meta):
			ev.protect_email_verification_fields(doc)
		self.assertEqual(doc._store["custom_email_verified"], 0)
		self.assertIsNone(doc._store["custom_email_verified_via"])

	def test_protect_fields_clears_on_new(self):
		meta = MagicMock()
		meta.has_field.return_value = True
		doc = self._doc(custom_email_verified=1, custom_email_verified_via="forged")
		doc.is_new.return_value = True
		with patch(f"{MODULE}.frappe.get_meta", return_value=meta):
			ev.protect_email_verification_fields(doc)
		self.assertEqual(doc._store["custom_email_verified"], 0)
		self.assertIsNone(doc._store["custom_email_verified_via"])

	def test_verification_fields_lists(self):
		from pos_next.api.constants import EMAIL_VERIFICATION_FIELDS

		self.assertIn("custom_email_verified_via", ev.VERIFICATION_FIELDS)
		self.assertIn("custom_email_verified_via", EMAIL_VERIFICATION_FIELDS)
