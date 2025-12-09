# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe

def get_base_value(doc, fieldname, base_fieldname=None, conversion_rate=None):
    from pos_next.api.utils.currency import get_base_value as _get_base_value
    return _get_base_value(doc, fieldname, base_fieldname, conversion_rate)

@frappe.whitelist()
def get_csrf_token():
	"""
	Get CSRF token for the current session.
	Only returns CSRF token if user is authenticated with a valid session.

	Security checks:
	- User must be authenticated (not Guest)
	- Session must be valid
	- User must be enabled

	Note: frappe.sessions.get_csrf_token() handles session updates and commits internally.
	"""
	# Check if user is authenticated
	if frappe.session.user == "Guest":
		frappe.throw("Authentication required", frappe.AuthenticationError)

	# Verify user is enabled
	if not frappe.db.get_value("User", frappe.session.user, "enabled"):
		frappe.throw("User is disabled", frappe.AuthenticationError)

	# Verify session exists and is valid
	if not frappe.session.sid or frappe.session.sid == "Guest":
		frappe.throw("Invalid session", frappe.AuthenticationError)

	# Get CSRF token for valid, authenticated session
	csrf_token = frappe.sessions.get_csrf_token()

	if not csrf_token:
		frappe.throw("Failed to generate CSRF token", frappe.ValidationError)

	return {
		"csrf_token": csrf_token,
		"session_id": frappe.session.sid
	}
