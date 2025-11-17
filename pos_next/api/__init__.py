# -*- coding: utf-8 -*-
# API module for POS Next

import frappe
from frappe.translate import get_all_translations

# Import API modules to make them accessible
from . import invoices
from . import items
from . import shifts
from . import pos_profile
from . import customers
from . import offers
from . import promotions
from . import utilities
from . import translations

@frappe.whitelist(allow_guest=True)
def ping():
    """Simple ping endpoint for connectivity checks"""
    return "pong"

@frappe.whitelist(allow_guest=True)
def get_translations(language=None):
    """Get all translations for the current user's language or specified language"""
    if not language:
        if frappe.session.user != "Guest":
            language = frappe.db.get_value("User", frappe.session.user, "language")
        else:
            language = frappe.db.get_single_value("System Settings", "language")

    return get_all_translations(language)

@frappe.whitelist(allow_guest=True)
def get_available_languages():
    """Get list of available languages from Language doctype"""
    languages = frappe.get_all(
        "Language",
        fields=["language_code", "language_name"],
        filters={"enabled": 1},
        order_by="language_name"
    )

    # Always include English as default
    if not any(lang["language_code"] == "en" for lang in languages):
        languages.insert(0, {"language_code": "en", "language_name": "English"})

    return languages
