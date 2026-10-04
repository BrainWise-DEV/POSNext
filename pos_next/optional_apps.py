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


# Optional apps the POS SPA checks via frappe.boot.<app> (see POS/src/utils/promoApi.js).
POS_BOOT_APP_FLAGS = ("posnext_promotions", "magento_integration")


def add_pos_app_flags(context):
	"""update_website_context hook: expose optional-app install flags as frappe.boot.<app> on /pos.

	The POS SPA has no Desk boot, and pos.html copies each boot key onto window.
	/pos is served to guests too, so only the flags the SPA reads are exposed.
	"""
	if (frappe.local.path or "").strip("/").split("/")[0] != "pos":
		return
	boot = context.get("boot")
	if not isinstance(boot, dict):
		return
	installed = set(frappe.get_installed_apps())
	flags = boot.setdefault("frappe", {}).setdefault("boot", {})
	flags.update({app: 1 for app in POS_BOOT_APP_FLAGS if app in installed})
