from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.api.constants import DEFAULT_POS_SETTINGS
from pos_next.integrations import otp
from pos_next.test_fixtures import ensure_pos_profile

NEW_KEYS = {
	"verification_provider": "",
	"otp_ttl_seconds": 900,
	"otp_resend_cooldown": 60,
	"otp_max_sends_per_hour": 5,
	"default_phone_country": "",
	"placeholder_email_domain": "",
	"require_split_name": 0,
}


def _fake(name):
	return SimpleNamespace(
		name=name,
		label=name,
		api=1,
		requires_phone=False,
		health=lambda: {"ok": True, "message": "", "fix_url": None},
		send=lambda ctx: {"ok": True, "code": "sent", "message": ""},
		verify=lambda ctx, otp_: {"ok": True, "code": "verified", "message": ""},
	)


class TestPOSSettingsVerification(FrappeTestCase):
	def setUp(self):
		frappe.local.pos_next_otp_providers = None
		self.addCleanup(lambda: setattr(frappe.local, "pos_next_otp_providers", None))

	def _profiles(self, n):
		return [ensure_pos_profile(f"_PNXT_TEST_VERIFY_PROFILE_{i}") for i in range(n)]

	def _settings_for(self, profile):
		name = frappe.db.get_value("POS Settings", {"pos_profile": profile})
		if name:
			return frappe.get_doc("POS Settings", name)
		doc = frappe.new_doc("POS Settings")
		doc.pos_profile = profile
		doc.enabled = 1
		doc.insert(ignore_permissions=True)
		return doc

	def test_defaults_present(self):
		for key, value in NEW_KEYS.items():
			self.assertIn(key, DEFAULT_POS_SETTINGS)
			self.assertEqual(DEFAULT_POS_SETTINGS[key], value)
		self.assertNotIn("miraaya_installed", DEFAULT_POS_SETTINGS)

	def test_all_settings_paths_return_fields(self):
		from pos_next.api import bootstrap
		from pos_next.api.pos_profile import get_pos_settings as profile_settings
		from pos_next.pos_next.doctype.pos_settings.pos_settings import get_pos_settings as desk_settings

		profile = self._profiles(1)[0]
		self._settings_for(profile)
		frappe.local.form_dict = frappe._dict(pos_profile=profile)
		# Bootstrap returns POS Settings only for the user's open shift: give it one on
		# this profile (a fresh site has none; a dev site's own shift is another profile).
		shift = frappe._dict(
			name="_PNXT_TEST_VERIFY_SHIFT",
			pos_profile=profile,
			period_start_date=frappe.utils.now_datetime(),
			status="Open",
			pos_profile_doc=frappe.get_doc("POS Profile", profile),
		)
		with patch.object(bootstrap, "_get_open_shift", return_value=shift):
			boot = bootstrap.get_initial_data()
		self.assertEqual(boot["pos_profile"]["name"], profile)
		paths = {
			"bootstrap": (boot.get("pos_settings") or {}),
			"pos_profile": profile_settings(profile),
			"desk": desk_settings(profile),
		}
		for label, settings in paths.items():
			for key in ("require_split_name", "placeholder_email_domain", "verification_provider"):
				self.assertIn(key, settings, f"{label} missing {key}")

	def test_two_profiles_two_providers(self):
		a, b = self._profiles(2)
		doc_a, doc_b = self._settings_for(a), self._settings_for(b)
		fakes = {"frappe_email": _fake("frappe_email"), "fake": _fake("fake")}
		with patch.object(otp, "get_providers", return_value=fakes):
			doc_a.verification_provider = "frappe_email"
			doc_a.save(ignore_permissions=True)
			doc_b.verification_provider = "fake"
			doc_b.save(ignore_permissions=True)
			self.assertEqual(otp.get_active_provider(a).name, "frappe_email")
			self.assertEqual(otp.get_active_provider(b).name, "fake")

	def test_unknown_provider_rejected(self):
		doc = self._settings_for(self._profiles(1)[0])
		doc.verification_provider = "nope"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)
