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
