# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Runtime checks for optional apps.

pos_next must not import those packages. Callers skip duplicate hooks and
monkey-patches when the owning app is installed.
"""

from __future__ import annotations

import frappe


def promotions_installed() -> bool:
	try:
		return "posnext_promotions" in frappe.get_installed_apps()
	except Exception:
		return False


# Optional apps the POS SPA switches on at runtime (see POS/src/utils/promoApi.js).
POS_UI_OPTIONAL_APPS = ("posnext_promotions", "magento_integration")


def get_pos_ui_app_flags() -> dict:
	"""{app_name: 1} for every optional POS app installed on this site."""
	try:
		installed = set(frappe.get_installed_apps())
	except Exception:
		return {}
	return {app: 1 for app in POS_UI_OPTIONAL_APPS if app in installed}


def update_pos_page_context(context):
	"""update_website_context hook: expose optional-app flags on the /pos page.

	/pos is not the Desk, so extend_bootinfo never runs there and
	window.frappe.boot is never set. The frappe-ui Jinja boot loop renders
	each key of ``context.boot`` as ``window[key]``, so this surfaces the flags
	as ``window.posnext_app_flags`` for the Vue app. Runs after the page's own
	get_context, so it extends (never replaces) its boot data.
	"""
	if (context.get("path") or "").strip("/") != "pos":
		return
	boot = dict(context.get("boot") or {})
	boot["posnext_app_flags"] = get_pos_ui_app_flags()
	# www/ is a gitignored build output, so a pos.py that sets the CSRF token is
	# not deployed with the app. Without a token in boot the Vue app starts with
	# no window.csrf_token and its first POSTs (frappe.auth.get_logged_user,
	# frappe.client.get_value) fail with CSRFTokenError. Set it here instead.
	if frappe.session.user != "Guest" and not boot.get("csrf_token"):
		boot["csrf_token"] = frappe.sessions.get_csrf_token()
	boot.setdefault("site_name", frappe.local.site)
	context.boot = boot
	# The page carries a per-session token: never serve it from the page cache.
	context.no_cache = 1
