# -*- coding: utf-8 -*-
# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import translate


@frappe.whitelist()
def get_app_translations():
	"""
	Get all translations for the current user's language.
	This is a wrapper around frappe.translate.get_all_translations
	since the original function is not whitelisted.

	Returns:
		dict: Translation dictionary {source: translated}
	"""
	lang = frappe.local.lang or "en"
	return translate.get_all_translations(lang)


@frappe.whitelist()
def get_user_language():
	"""
	Get the language preference for the current user.

	Returns:
		dict: User's language preference

	Security checks:
	- User must be authenticated (not Guest)
	"""
	# Check if user is authenticated
	if frappe.session.user == "Guest":
		frappe.throw("Authentication required", frappe.AuthenticationError)

	# Get user's language preference
	language = frappe.db.get_value("User", frappe.session.user, "language") or "en"

	return {
		"success": True,
		"locale": language.lower()
	}


@frappe.whitelist()
def get_allowed_locales():
	"""
	Get list of allowed locales from POS Settings for the language switcher.

	Returns:
		dict: List of allowed locale codes
	"""
	allowed = get_allowed_locales_from_settings()
	return {
		"success": True,
		"locales": list(allowed)
	}


def get_allowed_locales_from_settings():
	"""
	Get allowed locales from POS Settings.
	Falls back to default locales if not configured.

	Returns:
		set: Set of allowed locale codes
	"""
	default_locales = {'ar', 'en'}

	try:
		# Get the first POS Settings (or we could use a specific one based on user's profile)
		pos_settings_list = frappe.get_all(
			"POS Settings",
			filters={"enabled": 1},
			fields=["name"],
			limit=1
		)

		if not pos_settings_list:
			return default_locales

		pos_settings = frappe.get_doc("POS Settings", pos_settings_list[0].name)

		if pos_settings.allowed_locales and len(pos_settings.allowed_locales) > 0:
			return {row.language.lower() for row in pos_settings.allowed_locales}

		return default_locales
	except Exception:
		return default_locales


@frappe.whitelist()
def change_user_language(locale):
	"""
	Change the language preference for the current user.

	Args:
		locale (str): Language code (e.g., 'en', 'ar')

	Returns:
		dict: Success status and message

	Security checks:
	- User must be authenticated (not Guest)
	- User must be enabled
	"""
	# Check if user is authenticated
	if frappe.session.user == "Guest":
		frappe.throw("Authentication required", frappe.AuthenticationError)

	# Verify user is enabled
	if not frappe.db.get_value("User", frappe.session.user, "enabled"):
		frappe.throw("User is disabled", frappe.AuthenticationError)

	# Validate locale parameter
	if not locale:
		frappe.throw("Locale parameter is required", frappe.ValidationError)

	# Normalize locale to lowercase
	locale = locale.lower()

	allowed_locales = get_allowed_locales_from_settings()
	if locale not in allowed_locales:
		frappe.throw(f"Locale '{locale}' is not supported", frappe.ValidationError)

	# Update user's language preference
	try:
		frappe.db.set_value("User", frappe.session.user, "language", locale)
		frappe.db.commit()

		return {
			"success": True,
			"message": f"Language changed to {locale}",
			"locale": locale
		}
	except Exception as e:
		frappe.log_error(f"Failed to change user language: {str(e)}")
		frappe.throw(f"Failed to change language: {str(e)}", frappe.ValidationError)
