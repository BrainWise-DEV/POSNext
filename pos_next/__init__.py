# -*- coding: utf-8 -*-
from __future__ import unicode_literals

try:
    import frappe
except ModuleNotFoundError:  # pragma: no cover - frappe may not be installed during setup
    frappe = None

__version__ = "1.16.0"


def console(*data):
    """Publish data to browser console for debugging"""
    if frappe:
        frappe.publish_realtime("toconsole", data, user=frappe.session.user)


# Patch get_other_conditions to exclude pos_only pricing rules from non-POS documents.
# No Frappe hook exists for non-whitelisted module-level functions (override_whitelisted_methods
# only works for @frappe.whitelist() HTTP endpoints, override_doctype_class only for DocType
# classes). This is the standard Python module init approach — runs once at import.
try:
    from erpnext.accounts.doctype.pricing_rule import utils as pr_utils
    from pos_next.overrides.pricing_rule import patch_get_other_conditions
    patch_get_other_conditions(pr_utils)
except Exception:
    pass
