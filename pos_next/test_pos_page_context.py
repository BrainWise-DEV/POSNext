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
		self.assertEqual(context.boot, {"posnext_app_flags": {"posnext_promotions": 1}})

	def test_other_pages_untouched(self):
		context = frappe._dict(path="login")
		update_pos_page_context(context)
		self.assertNotIn("boot", context)

	def test_hook_registered(self):
		self.assertIn(
			"pos_next.optional_apps.update_pos_page_context",
			frappe.get_hooks("update_website_context"),
		)
