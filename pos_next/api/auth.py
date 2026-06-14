# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils.password import check_password


@frappe.whitelist()
@rate_limit(limit=5, seconds=60)
def verify_session_password(password=None):
    """Verify the current session user's password for session lock re-authentication.

    NOTE: We must NOT raise frappe.AuthenticationError here because Frappe's
    error handler (app.py) calls login_manager.clear_cookies() for that
    exception type, which would destroy the user's session on a wrong password.
    Instead, we return a structured response indicating success or failure.
    """
    if not password:
        return {"verified": False, "message": _("Password is required")}

    try:
        check_password(frappe.session.user, password)
        return {"verified": True}
    except frappe.AuthenticationError:
        return {"verified": False, "message": _("Incorrect password")}
