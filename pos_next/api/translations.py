# -*- coding: utf-8 -*-
"""Translation API for POS Next with caching and optimization."""

import frappe
import os
from frappe.utils import add_to_date, get_datetime

# Language display names mapping
LANGUAGE_NAMES = {
    "en": "English",
    "ar": "العربية",
    "es": "Español",
}

# RTL languages list
RTL_LANGUAGES = ["ar", "he", "fa", "ur"]

# Cache for language data
_LANGUAGE_CACHE = {
    "languages": None,
    "last_updated": None,
    "cache_duration": 300,  # 5 minutes
}


def _is_cache_valid():
    """Check if language cache is still valid."""
    if not _LANGUAGE_CACHE["last_updated"]:
        return False
    cache_time = _LANGUAGE_CACHE["last_updated"]
    expiry_time = add_to_date(cache_time, seconds=_LANGUAGE_CACHE["cache_duration"])
    return get_datetime() < expiry_time


def _update_language_cache(languages):
    """Update the language cache."""
    _LANGUAGE_CACHE["languages"] = languages
    _LANGUAGE_CACHE["last_updated"] = get_datetime()


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def get_available_languages():
    """Get list of available languages with caching."""
    # Return cached data if valid
    if _is_cache_valid() and _LANGUAGE_CACHE["languages"]:
        return _LANGUAGE_CACHE["languages"]

    languages = []

    try:
        translations_path = frappe.get_app_path("pos_next", "translations")
        if os.path.exists(translations_path):
            with os.scandir(translations_path) as entries:
                for entry in entries:
                    if entry.is_file() and entry.name.endswith(".csv"):
                        lang_code = os.path.splitext(entry.name)[0]
                        display_name = LANGUAGE_NAMES.get(lang_code, lang_code.upper())
                        languages.append({
                            "code": lang_code,
                            "name": display_name,
                            "is_rtl": lang_code in RTL_LANGUAGES
                        })

        # Always include English as fallback
        if not any(lang["code"] == "en" for lang in languages):
            languages.insert(0, {"code": "en", "name": "English", "is_rtl": False})

        # Sort by code
        languages = sorted(languages, key=lambda x: x["code"])
        _update_language_cache(languages)

        return languages

    except Exception as e:
        frappe.log_error(f"Error getting available languages: {str(e)}")
        fallback = [{"code": "en", "name": "English", "is_rtl": False}]
        _update_language_cache(fallback)
        return fallback


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def get_translation_dict(lang_code=None):
    """Get translation dictionary for a specific language."""
    if not lang_code:
        # Get user language or system default
        if frappe.session.user != "Guest":
            lang_code = frappe.db.get_value("User", frappe.session.user, "language") or "en"
        else:
            lang_code = frappe.db.get_single_value("System Settings", "language") or "en"

    # English is the base language
    if lang_code == "en":
        return {}

    translations = {}

    try:
        translations_path = frappe.get_app_path("pos_next", "translations", f"{lang_code}.csv")

        if os.path.exists(translations_path):
            import csv
            with open(translations_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2:
                        source_text = row[0].strip()
                        translated_text = row[1].strip()
                        if source_text and translated_text:
                            translations[source_text] = translated_text

        return translations

    except Exception as e:
        frappe.log_error(f"Error loading translations for {lang_code}: {str(e)}")
        return {}


@frappe.whitelist()
def set_user_language(lang_code):
    """Set the current user's language preference."""
    try:
        user = frappe.session.user
        if user == "Guest":
            return {"success": False, "message": "Guest users cannot set language preferences"}

        # Validate language code
        available_languages = get_available_languages()
        valid_codes = [lang["code"] for lang in available_languages]

        if lang_code not in valid_codes:
            return {"success": False, "message": f"Language '{lang_code}' is not supported"}

        # Update user language
        frappe.db.set_value("User", user, "language", lang_code, update_modified=False)
        frappe.db.commit()

        # Clear caches
        frappe.clear_cache(user=user)

        return {
            "success": True,
            "message": f"Language changed to {lang_code}",
            "language": lang_code
        }

    except Exception as e:
        frappe.log_error(f"Error setting language: {str(e)}")
        return {"success": False, "message": "Failed to set language"}
