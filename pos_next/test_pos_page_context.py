# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""/pos page exposes optional-app flags (window.posnext_app_flags) for the Vue app."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.optional_apps import get_pos_ui_app_flags, update_pos_page_context


class TestPosPageContext(FrappeTestCase):
	def test_flags_follow_installed_apps(self):
		with patch("frappe.get_installed_apps", return_value=["frappe", "erpnext", "posnext_promotions"]):
			self.assertEqual(get_pos_ui_app_flags(), {"posnext_promotions": 1})
		with patch("frappe.get_installed_apps", return_value=["frappe", "erpnext"]):
			self.assertEqual(get_pos_ui_app_flags(), {})

	def test_extends_existing_boot_on_pos_page(self):
		context = frappe._dict(path="pos", boot={"csrf_token": "x", "site_name": "s"})
		with patch("frappe.get_installed_apps", return_value=["posnext_promotions"]):
			update_pos_page_context(context)
		self.assertEqual(context.boot["csrf_token"], "x")
		self.assertEqual(context.boot["posnext_app_flags"], {"posnext_promotions": 1})

	def test_creates_boot_when_page_has_none(self):
		context = frappe._dict(path="pos")
		with patch("frappe.get_installed_apps", return_value=["posnext_promotions"]):
			update_pos_page_context(context)
		self.assertEqual(context.boot["posnext_app_flags"], {"posnext_promotions": 1})
		self.assertEqual(context.boot["site_name"], frappe.local.site)
		self.assertIn("posnext_developer_mode", context.boot)

	def test_logged_in_boot_carries_session_csrf_token(self):
		# www/pos.py is not deployed (www/ is gitignored); without this the POS
		# starts with no CSRF token and its first POSTs fail with CSRFTokenError.
		context = frappe._dict(path="pos")
		with patch("frappe.sessions.get_csrf_token", return_value="tok-123"):
			update_pos_page_context(context)
		self.assertEqual(context.boot["csrf_token"], "tok-123")
		self.assertTrue(context.no_cache)

	def test_guest_boot_has_no_csrf_token(self):
		context = frappe._dict(path="pos")
		user = frappe.session.user
		frappe.set_user("Guest")
		try:
			update_pos_page_context(context)
		finally:
			frappe.set_user(user)
		self.assertNotIn("csrf_token", context.boot)

	def test_exposes_backend_developer_mode(self):
		for flag in (0, 1):
			context = frappe._dict(path="pos")
			with patch.dict(frappe.conf, {"developer_mode": flag}):
				update_pos_page_context(context)
			self.assertEqual(context.boot["posnext_developer_mode"], flag)

	def test_other_pages_untouched(self):
		context = frappe._dict(path="login")
		update_pos_page_context(context)
		self.assertNotIn("boot", context)

	def test_hook_registered(self):
		self.assertIn(
			"pos_next.optional_apps.update_pos_page_context",
			frappe.get_hooks("update_website_context"),
		)


class TestPosAssetVersions(FrappeTestCase):
	"""?v= of each optional app's POS scripts: a new release is a new URL (G7)."""

	def test_boot_carries_a_content_hash_per_optional_app(self):
		import os
		import tempfile

		from pos_next.optional_apps import get_pos_asset_versions

		with tempfile.TemporaryDirectory() as app_dir:
			pos_dir = os.path.join(app_dir, "public", "pos")
			os.makedirs(pos_dir)
			script = os.path.join(pos_dir, "offer-strategies.js")
			with open(script, "w") as f:
				f.write("export const a = 1;")
			with (
				patch("frappe.get_installed_apps", return_value=["posnext_promotions"]),
				patch("frappe.get_app_path", side_effect=lambda app, *parts: os.path.join(app_dir, *parts)),
			):
				first = get_pos_asset_versions()
				self.assertEqual(list(first), ["posnext_promotions"])
				self.assertRegex(first["posnext_promotions"], r"^[0-9a-f]{12}$")
				self.assertEqual(get_pos_asset_versions(), first)

				with open(script, "w") as f:
					f.write("export const a = 22;")
				self.assertNotEqual(get_pos_asset_versions(), first)

				context = frappe._dict(path="pos")
				with patch("frappe.sessions.get_csrf_token", return_value="tok"):
					update_pos_page_context(context)
				self.assertEqual(context.boot["posnext_asset_versions"], get_pos_asset_versions())

	def test_no_optional_app_no_versions(self):
		from pos_next.optional_apps import get_pos_asset_versions

		with patch("frappe.get_installed_apps", return_value=["frappe", "erpnext"]):
			self.assertEqual(get_pos_asset_versions(), {})
