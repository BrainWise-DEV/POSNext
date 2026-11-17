from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.integrations import otp

BUILTIN = "pos_next.integrations.otp_frappe_email.get_provider"


def _fake(name="fake", api=1):
	return SimpleNamespace(
		name=name,
		label=name,
		api=api,
		requires_phone=False,
		health=lambda: {"ok": True, "message": "", "fix_url": None},
		send=lambda ctx: {"ok": True, "code": "sent", "message": ""},
		verify=lambda ctx, otp_: {"ok": True, "code": "verified", "message": ""},
	)


def _raise():
	raise RuntimeError("boom")


class TestOtpRegistry(FrappeTestCase):
	def setUp(self):
		frappe.local.pos_next_otp_providers = None
		self.addCleanup(lambda: setattr(frappe.local, "pos_next_otp_providers", None))

	def _providers(self, factories):
		hooks = {"pos_next_email_otp_providers": [BUILTIN, *[f"x.{i}" for i in range(len(factories))]]}
		frappe.local.pos_next_otp_providers = None
		real = frappe.get_attr
		fmap = {f"x.{i}": f for i, f in enumerate(factories)}
		with (
			patch.object(frappe, "get_hooks", lambda k, *a, **kw: hooks.get(k, [])),
			patch.object(frappe, "get_attr", lambda p: fmap.get(p) or real(p)),
			patch.object(frappe, "log_error") as log_error,
		):
			self.log_error = log_error
			return otp.get_providers()

	def test_builtin_provider_listed(self):
		frappe.local.pos_next_otp_providers = None
		self.assertIn("frappe_email", otp.get_providers())

	def test_wrong_api_version_dropped(self):
		self.assertNotIn("fake", self._providers([lambda: _fake(api=2)]))
		self.log_error.assert_called()

	def test_raising_factory_dropped(self):
		providers = self._providers([_raise])
		self.assertIn("frappe_email", providers)
		self.log_error.assert_called()

	def test_duplicate_name_dropped(self):
		first, second = _fake("dup"), _fake("dup")
		providers = self._providers([lambda: first, lambda: second])
		self.assertIs(providers["dup"], first)
		self.log_error.assert_called()

	def test_active_provider_default(self):
		frappe.local.pos_next_otp_providers = None
		self.assertEqual(otp.get_active_provider(None).name, "frappe_email")

	def test_call_provider_bad_result(self):
		with patch.object(frappe, "log_error"):
			res = otp.call_provider(lambda: {"foo": 1})
			self.assertEqual(res, {"ok": False, "code": "unavailable"})
			self.assertEqual(otp.call_provider(_raise)["code"], "unavailable")
			self.assertEqual(otp.call_provider(lambda: {"ok": True, "code": "weird"})["code"], "unavailable")

	def test_provider_options_requires_write_permission(self):
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			otp.get_provider_options()
		frappe.set_user("Administrator")
		frappe.local.pos_next_otp_providers = None
		names = [o["name"] for o in otp.get_provider_options()]
		self.assertIn("frappe_email", names)
