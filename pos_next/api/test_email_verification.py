# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Unit tests for the customer email OTP flow. Magento, settings and cache are mocked."""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe
import requests

from pos_next.api import email_verification as ev

OTP = "482913"
TOKEN = "SECRET-BEARER-TOKEN-xyz"
MODULE = "pos_next.api.email_verification"
ORIGINAL_AUDIT = ev._audit


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


class FakeResponse:
	def __init__(self, status=200, body=None):
		self.status_code = status
		self._body = body

	def json(self):
		if self._body is None:
			raise ValueError("no json")
		return self._body


CUSTOMER_ROW = frappe._dict(
	name="CUST-1",
	mobile_no="964-7701234567",
	email_id="jane@example.com",
	custom_customer_id=55,
)


class EmailOTPTestBase(unittest.TestCase):
	def setUp(self):
		self.cache = FakeCache()
		self.row = frappe._dict(CUSTOMER_ROW)
		meta = MagicMock()
		meta.has_field.return_value = True
		self.patches = [
			patch(f"{MODULE}._cache", return_value=self.cache),
			patch(f"{MODULE}.is_feature_enabled", return_value=True),
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_meta", return_value=meta),
			patch(f"{MODULE}.frappe.db.get_value", side_effect=lambda *a, **k: self.row),
			patch(
				f"{MODULE}._get_magento_config",
				return_value=("https://magento.test", {"Authorization": f"Bearer {TOKEN}"}),
			),
			patch(f"{MODULE}._audit"),
			patch(f"{MODULE}._mark_verified"),
			patch(f"{MODULE}.frappe.log_error"),
		]
		mocks = [p.start() for p in self.patches]
		self.mock_audit = mocks[6]
		self.mock_mark = mocks[7]
		self.mock_log_error = mocks[8]
		self.addCleanup(lambda: [p.stop() for p in self.patches])

	def post(self, status=200, body=None):
		return patch(f"{MODULE}.requests.post", return_value=FakeResponse(status, body))


class TestPhoneNormalization(unittest.TestCase):
	def test_table(self):
		good = "+9647701234567"
		cases = {
			"964-7701234567": good,
			"+9647701234567": good,
			"009647701234567": good,
			"07701234567": good,
			"7701234567": good,
			"+964 770 123 4567": good,
			"(0770) 123-4567": good,
			"٠٧٧٠١٢٣٤٥٦٧": good,
			"+٩٦٤٧٧٠١٢٣٤٥٦٧": good,
			"964-07701234567": good,
			"": None,
			None: None,
			"12345": None,
			"0660123456": None,
			"+201001234567": None,
			"770123456": None,
			"77012345678": None,
			"abc7701234567": None,
		}
		for raw, expected in cases.items():
			self.assertEqual(ev.normalize_iraqi_phone(raw), expected, raw)

	def test_fabricated_email(self):
		self.assertTrue(ev.is_fabricated_email("pos.7701234567@pos.miraaya"))
		self.assertTrue(ev.is_fabricated_email("POS.1@POS.MIRAAYA"))
		self.assertFalse(ev.is_fabricated_email("a@miraaya.com"))


class TestSend(EmailOTPTestBase):
	def test_success_posts_normalized_phone_server_side(self):
		with self.post(200, {"success": True, "otp_required": True}) as m:
			res = ev.send_email_otp("CUST-1", "jane@example.com")
		self.assertTrue(res["ok"])
		self.assertEqual(res["code"], "sent")
		self.assertEqual(res["expires_in"], 900)
		self.assertEqual(res["resend_in"], 60)
		args, kwargs = m.call_args
		self.assertEqual(args[0], "https://magento.test" + ev.SEND_ENDPOINT)
		self.assertEqual(kwargs["json"], {"phone": "+9647701234567", "email": "jane@example.com"})
		self.assertEqual(kwargs["timeout"], (5, 20))

	def test_error_mappings(self):
		table = [
			(400, "Phone is required.", "phone_required"),
			(400, "Invalid Phone Number. Use Iraqi format", "invalid_phone"),
			(400, "A valid email address is required.", "invalid_email"),
			(400, "No customer was found with this phone", "customer_not_found"),
			(400, "Email is already registered to another account", "email_taken"),
			(500, "Unable to store the verification code", "server_error"),
			(502, "bad gateway", "server_error"),
			(401, "Unauthorized", "credentials_invalid"),
			(403, "Forbidden", "credentials_invalid"),
			(400, "Something odd", "send_failed"),
		]
		for status, message, code in table:
			self.cache.store.clear()
			with self.post(status, {"message": message}):
				res = ev.send_email_otp("CUST-1")
			self.assertFalse(res["ok"], message)
			self.assertEqual(res["code"], code, message)

	def test_timeout_and_connection_error(self):
		for exc in (requests.exceptions.Timeout(), requests.exceptions.ConnectionError()):
			self.cache.store.clear()
			with patch(f"{MODULE}.requests.post", side_effect=exc):
				res = ev.send_email_otp("CUST-1")
			self.assertEqual(res["code"], "unavailable")
			self.assertFalse(res["ok"])

	def test_success_false_body_not_ok(self):
		with self.post(200, {"success": False, "message": "No customer was found"}):
			res = ev.send_email_otp("CUST-1")
		self.assertFalse(res["ok"])
		self.assertEqual(res["code"], "customer_not_found")

	def test_otp_not_required_does_not_mark_verified(self):
		with self.post(200, {"success": True, "otp_required": False}):
			res = ev.send_email_otp("CUST-1")
		self.assertEqual(res["code"], "otp_not_required")
		self.mock_mark.assert_not_called()

	def test_new_customer_without_magento_id_still_sends(self):
		# New POS customer: no custom_customer_id yet, but Magento knows the phone.
		self.row.custom_customer_id = None
		with self.post(200, {"success": True, "otp_required": True}) as m:
			res = ev.send_email_otp("CUST-1", "jane@example.com")
		self.assertEqual((res["ok"], res["code"]), (True, "sent"))
		m.assert_called_once()
		self.assertEqual(m.call_args.kwargs["json"]["phone"], "+9647701234567")

	def test_new_customer_unknown_to_magento_is_sync_pending(self):
		self.row.custom_customer_id = None
		for status, body in (
			(400, {"message": "No customer was found with this phone"}),
			(200, {"success": False, "message": "No customer was found"}),
		):
			with self.subTest(status=status), self.post(status, body):
				res = ev.send_email_otp("CUST-1")
			self.assertEqual((res["ok"], res["code"]), (False, "sync_pending"))
			self.assertNotEqual(res["message"], ev._messages()["customer_not_found"])

	def test_synced_customer_unknown_to_magento_stays_customer_not_found(self):
		with self.post(400, {"message": "No customer was found with this phone"}):
			res = ev.send_email_otp("CUST-1")
		self.assertEqual(res["code"], "customer_not_found")

	def test_not_found_and_sync_pending_messages_differ(self):
		msgs = ev._messages()
		self.assertNotEqual(msgs["customer_not_found"], msgs["sync_pending"])
		self.assertNotIn("not registered", msgs["sync_pending"])

	def test_other_errors_unchanged_when_not_synced(self):
		self.row.custom_customer_id = None
		with self.post(400, {"message": "This email is already registered"}):
			self.assertEqual(ev.send_email_otp("CUST-1")["code"], "email_taken")

	def test_flag_off(self):
		with patch(f"{MODULE}.is_feature_enabled", return_value=False), self.post(200, {}) as m:
			res = ev.send_email_otp("CUST-1")
		self.assertEqual((res["ok"], res["code"]), (False, "disabled"))
		m.assert_not_called()

	def test_permission_denied(self):
		with patch(f"{MODULE}.frappe.has_permission", return_value=False), self.post(200, {}) as m:
			with self.assertRaises(frappe.PermissionError):
				ev.send_email_otp("CUST-1")
		m.assert_not_called()

	def test_magento_not_configured(self):
		with patch(f"{MODULE}._get_magento_config", return_value=None), self.post(200, {}) as m:
			res = ev.send_email_otp("CUST-1")
		self.assertEqual(res["code"], "not_configured")
		self.assertIn("Magento not configured", res["message"])
		m.assert_not_called()

	def test_blank_and_fabricated_email_rejected(self):
		for email in ("", None, "pos.7701234567@pos.miraaya", "not-an-email"):
			self.row.email_id = email
			with self.post(200, {}) as m:
				res = ev.send_email_otp("CUST-1")
			self.assertEqual(res["code"], "invalid_email", email)
			m.assert_not_called()

	def test_email_param_must_match_saved(self):
		with self.post(200, {}) as m:
			res = ev.send_email_otp("CUST-1", "other@example.com")
		self.assertEqual(res["code"], "email_not_saved")
		m.assert_not_called()

	def test_phone_errors(self):
		self.row.mobile_no = ""
		self.assertEqual(ev.send_email_otp("CUST-1")["code"], "phone_required")
		self.row.mobile_no = "12345"
		self.assertEqual(ev.send_email_otp("CUST-1")["code"], "invalid_phone")

	def test_cooldown_and_hourly_cap(self):
		with self.post(200, {"success": True}) as m:
			self.assertTrue(ev.send_email_otp("CUST-1")["ok"])
			res = ev.send_email_otp("CUST-1")
		self.assertEqual(res["code"], "too_many_attempts")
		self.assertGreater(res["retry_after"], 0)
		self.assertEqual(m.call_count, 1)

		# 5 sends in the last hour, last one outside the cooldown
		now = __import__("time").time()
		state = ev._load_state("CUST-1")
		state["sends"] = [now - 3000, now - 2500, now - 2000, now - 1500, now - 200]
		ev._save_state("CUST-1", state)
		with self.post(200, {"success": True}) as m:
			res = ev.send_email_otp("CUST-1")
		self.assertEqual(res["code"], "too_many_attempts")
		self.assertGreater(res["retry_after"], 60)
		m.assert_not_called()

	def test_lock_busy(self):
		lock = MagicMock()
		lock.acquire.return_value = False
		self.cache.lock = lambda *a, **k: lock
		with self.post(200, {"success": True}) as m:
			res = ev.send_email_otp("CUST-1")
		self.assertEqual(res["code"], "busy")
		m.assert_not_called()


class TestVerify(EmailOTPTestBase):
	def test_success_only_when_status_true(self):
		with self.post(200, {"status": True, "message": "Verified"}) as m:
			res = ev.verify_email_otp("CUST-1", OTP, "jane@example.com")
		self.assertTrue(res["ok"])
		self.assertEqual(res["code"], "verified")
		self.mock_mark.assert_called_once_with("CUST-1", "jane@example.com")
		self.assertEqual(
			m.call_args.kwargs["json"],
			{"phone": "+9647701234567", "email": "jane@example.com", "otp": OTP},
		)

	def test_http_200_status_false_is_never_success(self):
		cases = [
			({"status": False, "message": "Verification code expired"}, "expired"),
			({"status": False, "message": "Invalid verification code"}, "invalid_otp"),
			({"status": False, "message": "Email is already registered to another account"}, "email_taken"),
			({"status": False, "message": "No customer was found"}, "customer_not_found"),
			({"status": False, "message": "Something else"}, "verify_failed"),
			({"status": False}, "verify_failed"),
			({}, "verify_failed"),
			({"status": "false"}, "verify_failed"),
			({"status": "true"}, "verify_failed"),
			({"message": "ok"}, "verify_failed"),
		]
		for body, code in cases:
			with self.post(200, body):
				res = ev.verify_email_otp("CUST-1", OTP)
			self.assertFalse(res["ok"], body)
			self.assertEqual(res["code"], code, body)
		self.mock_mark.assert_not_called()

	def test_http_errors(self):
		for status, message, code in [
			(400, "Invalid Phone Number.", "invalid_phone"),
			(400, "A valid email address is required.", "invalid_email"),
			(500, "boom", "server_error"),
			(401, "x", "credentials_invalid"),
		]:
			with self.post(status, {"message": message}):
				res = ev.verify_email_otp("CUST-1", OTP)
			self.assertEqual((res["ok"], res["code"]), (False, code))
		self.mock_mark.assert_not_called()

	def test_non_json_body_not_success(self):
		with self.post(200, None):
			res = ev.verify_email_otp("CUST-1", OTP)
		self.assertFalse(res["ok"])

	def test_bad_otp_format_no_request(self):
		for otp in ("", "12345", "1234567", "abcdef", None):
			with self.post(200, {"status": True}) as m:
				res = ev.verify_email_otp("CUST-1", otp)
			self.assertEqual(res["code"], "invalid_otp")
			m.assert_not_called()

	def test_arabic_digit_otp_normalized(self):
		with self.post(200, {"status": True}) as m:
			ev.verify_email_otp("CUST-1", "٤٨٢٩١٣")
		self.assertEqual(m.call_args.kwargs["json"]["otp"], OTP)

	def test_unavailable(self):
		with patch(f"{MODULE}.requests.post", side_effect=requests.exceptions.Timeout()):
			res = ev.verify_email_otp("CUST-1", OTP)
		self.assertEqual(res["code"], "unavailable")

	def test_attempt_cap(self):
		with self.post(200, {"status": False, "message": "Invalid verification code"}) as m:
			for _i in range(ev.MAX_VERIFY_ATTEMPTS):
				self.assertEqual(ev.verify_email_otp("CUST-1", OTP)["code"], "invalid_otp")
			res = ev.verify_email_otp("CUST-1", OTP)
		self.assertEqual(res["code"], "too_many_attempts")
		self.assertEqual(m.call_count, ev.MAX_VERIFY_ATTEMPTS)

	def test_new_send_resets_attempts(self):
		with self.post(200, {"status": False, "message": "Invalid verification code"}):
			for _i in range(3):
				ev.verify_email_otp("CUST-1", OTP)
		self.assertEqual(ev._load_state("CUST-1")["attempts"], 3)
		with self.post(200, {"success": True}):
			ev.send_email_otp("CUST-1")
		self.assertEqual(ev._load_state("CUST-1")["attempts"], 0)

	def test_flag_off_not_synced_permission(self):
		with patch(f"{MODULE}.is_feature_enabled", return_value=False):
			self.assertEqual(ev.verify_email_otp("CUST-1", OTP)["code"], "disabled")
		self.row.custom_customer_id = 0
		with self.post(200, {"status": False, "message": "No customer was found"}):
			self.assertEqual(ev.verify_email_otp("CUST-1", OTP)["code"], "sync_pending")
		with self.post(200, {"status": True}):
			self.assertEqual(ev.verify_email_otp("CUST-1", OTP)["code"], "verified")
		with patch(f"{MODULE}.frappe.has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				ev.verify_email_otp("CUST-1", OTP)


class TestSecrets(EmailOTPTestBase):
	def _all_recorded_text(self, results):
		parts = [json.dumps(results, default=str)]
		parts += [str(c) for c in self.mock_audit.call_args_list]
		parts += [str(c) for c in self.mock_log_error.call_args_list]
		parts += [json.dumps(self.cache.store, default=str)]
		return "\n".join(parts)

	def test_otp_and_token_never_logged_or_stored(self):
		results = []
		bodies = [
			(200, {"status": False, "message": "Invalid verification code"}),
			(200, {"status": True}),
			(500, {"message": "boom"}),
			(401, {"message": "nope"}),
		]
		for status, body in bodies:
			with self.post(status, body):
				results.append(ev.verify_email_otp("CUST-1", OTP))
		with self.post(500, {"message": "Unable to store"}):
			results.append(ev.send_email_otp("CUST-1"))
		text = self._all_recorded_text(results)
		self.assertNotIn(OTP, text)
		self.assertNotIn(TOKEN, text)
		self.assertTrue(self.mock_log_error.called)

	def test_audit_text_has_no_otp(self):
		doc = MagicMock()
		with patch(f"{MODULE}.frappe.get_doc", return_value=doc):
			ORIGINAL_AUDIT("CUST-1", "verify", "invalid_otp", "jane@example.com", "+9647701234567", 200)
		text = doc.add_comment.call_args.args[1]
		self.assertNotIn(OTP, text)
		self.assertNotIn("+9647701234567", text)  # phone is masked
		self.assertIn("invalid_otp", text)


class TestDocEvents(unittest.TestCase):
	def _doc(self, **values):
		doc = MagicMock()
		store = dict(values)
		doc.get.side_effect = lambda k, d=None: store.get(k, d)
		doc.set.side_effect = lambda k, v: store.__setitem__(k, v)
		doc._store = store
		return doc

	def test_reset_on_email_change(self):
		doc = self._doc(
			custom_email_verified=1, custom_verified_email="a@x.com", email_id="b@x.com"
		)
		ev.reset_email_verification_on_email_change(doc)
		doc.db_set.assert_called_once()
		self.assertEqual(doc.db_set.call_args.args[0]["custom_email_verified"], 0)
		self.assertEqual(doc._store["custom_email_verified"], 0)

	def test_no_reset_when_same_email_case_insensitive(self):
		doc = self._doc(
			custom_email_verified=1, custom_verified_email="a@x.com", email_id="A@X.com"
		)
		ev.reset_email_verification_on_email_change(doc)
		doc.db_set.assert_not_called()

	def test_no_reset_when_not_verified(self):
		doc = self._doc(custom_email_verified=0, email_id="b@x.com")
		ev.reset_email_verification_on_email_change(doc)
		doc.db_set.assert_not_called()

	def test_protect_fields_reverts_client_changes(self):
		meta = MagicMock()
		meta.has_field.return_value = True
		doc = self._doc(custom_email_verified=1)
		doc.is_new.return_value = False
		doc.get_doc_before_save.return_value = frappe._dict(custom_email_verified=0)
		with patch(f"{MODULE}.frappe.get_meta", return_value=meta):
			ev.protect_email_verification_fields(doc)
		self.assertEqual(doc._store["custom_email_verified"], 0)
