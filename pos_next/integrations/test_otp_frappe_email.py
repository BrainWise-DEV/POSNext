import re
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.integrations import otp_frappe_email as mod
from pos_next.integrations.otp import OtpContext

CUST = "_Test OTP Customer"


def _ctx(email="a@example.com"):
	return OtpContext(customer=CUST, email=email)


class TestOtpFrappeEmail(FrappeTestCase):
	def setUp(self):
		self.p = mod.get_provider()
		mod.clear_code(CUST)
		self.addCleanup(mod.clear_code, CUST)

	def _send(self, ctx=None):
		with patch.object(frappe, "sendmail") as sm:
			res = self.p.send(ctx or _ctx())
		code = sm.call_args.kwargs["args"]["code"] if sm.called else None
		return res, code, sm

	def test_send_then_verify(self):
		res, code, sm = self._send()
		self.assertEqual(res["code"], "sent")
		self.assertTrue(re.fullmatch(r"\d{6}", code))
		self.assertEqual(sm.call_args.kwargs["template"], "customer_email_otp")
		self.assertEqual(sm.call_args.kwargs["recipients"], ["a@example.com"])
		self.assertEqual(self.p.verify(_ctx(), code)["code"], "verified")
		self.assertEqual(self.p.verify(_ctx(), code)["code"], "expired")

	def test_wrong_code(self):
		_, code, _ = self._send()
		wrong = f"{(int(code) + 1) % 10**6:06d}"
		self.assertEqual(self.p.verify(_ctx(), wrong)["code"], "invalid_otp")

	def test_expired(self):
		_, code, _ = self._send()
		mod.clear_code(CUST)
		self.assertEqual(self.p.verify(_ctx(), code)["code"], "expired")

	def test_code_bound_to_email(self):
		_, code, _ = self._send(_ctx("a@example.com"))
		self.assertEqual(self.p.verify(_ctx("b@example.com"), code)["code"], "invalid_otp")

	def test_code_not_in_logs_or_result(self):
		res, code, _ = self._send()
		blob = str(res) + str(frappe.cache().get_value(mod._key(CUST)))
		self.assertNotIn(code, blob)
		for dt, field in (("Comment", "content"), ("Error Log", "error")):
			for row in frappe.get_all(dt, fields=[field], order_by="creation desc", limit=20):
				self.assertNotIn(code, row[field] or "")

	def test_template_renders_code(self):
		html = frappe.render_template(
			"templates/emails/customer_email_otp.html", {"code": "123456", "minutes": 15, "company": "Acme"}
		)
		self.assertIn("123456", html)
		self.assertIn("15", html)

	def test_send_failure_cleans_up(self):
		with patch.object(frappe, "sendmail", side_effect=frappe.OutgoingEmailError("x")):
			res = self.p.send(_ctx())
		self.assertEqual(res["code"], "unavailable")
		self.assertIsNone(frappe.cache().get_value(mod._key(CUST)))

	def test_send_failure_leaks_no_code(self):
		with patch.object(frappe, "sendmail", side_effect=RuntimeError("boom")) as sm:
			res = self.p.send(_ctx())
		self.assertEqual(res["code"], "unavailable")
		code = sm.call_args.kwargs["args"]["code"]
		self.assertNotIn(code, str(res))
		self.assertIsNone(frappe.cache().get_value(mod._key(CUST)))
		for row in frappe.get_all("Error Log", fields=["error", "method"], order_by="creation desc", limit=20):
			self.assertNotIn(code, (row.error or "") + (row.method or ""))

	def test_sendmail_redacts_message(self):
		_, _, sm = self._send()
		self.assertTrue(sm.call_args.kwargs["redact_message_after_send"])

	def test_customer_save_without_email_change_keeps_code(self):
		from pos_next.api.email_verification import reset_email_verification_on_email_change

		self._send()
		doc = frappe._dict(name=CUST, custom_email_verified=1, email_id="a@example.com",
			custom_verified_email="a@example.com")
		doc.has_value_changed = lambda f: False
		reset_email_verification_on_email_change(doc)
		self.assertIsNotNone(frappe.cache().get_value(mod._key(CUST)))
		doc.has_value_changed = lambda f: True
		reset_email_verification_on_email_change(doc)
		self.assertIsNone(frappe.cache().get_value(mod._key(CUST)))

	def test_resend_replaces_code(self):
		_, old, _ = self._send()
		new = old
		while new == old:
			_, new, _ = self._send()
		self.assertEqual(self.p.verify(_ctx(), old)["code"], "invalid_otp")
		self.assertEqual(self.p.verify(_ctx(), new)["code"], "verified")

	def test_health_without_email_account(self):
		with (
			patch.object(frappe.db, "get_value", return_value=None),
			patch.object(frappe, "conf", frappe._dict()),
		):
			h = self.p.health()
		self.assertFalse(h["ok"])
		self.assertEqual(h["fix_url"], "/app/email-account")

	def test_health_ok_on_dev_site(self):
		if not frappe.db.get_value("Email Account", {"default_outgoing": 1, "enable_outgoing": 1}):
			self.skipTest("no default outgoing Email Account")
		self.assertTrue(self.p.health()["ok"])
