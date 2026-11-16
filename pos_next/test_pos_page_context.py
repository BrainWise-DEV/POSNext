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

	def test_other_pages_untouched(self):
		context = frappe._dict(path="login")
		update_pos_page_context(context)
		self.assertNotIn("boot", context)

	def test_hook_registered(self):
		self.assertIn(
			"pos_next.optional_apps.update_pos_page_context",
			frappe.get_hooks("update_website_context"),
		)
