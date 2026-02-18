# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.utils.password import check_password


@frappe.whitelist()
def verify_session_password(password):
    """Verify the current session user's password for session lock re-authentication."""
    try:
        check_password(frappe.session.user, password)
        return {"verified": True}
    except frappe.AuthenticationError:
        frappe.throw(_("Incorrect password"), frappe.AuthenticationError)
