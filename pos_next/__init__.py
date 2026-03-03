# -*- coding: utf-8 -*-
from __future__ import unicode_literals

try:
    import frappe
except ModuleNotFoundError:  # pragma: no cover - frappe may not be installed during setup
    frappe = None

__version__ = "1.15.0"


def console(*data):
    """Publish data to browser console for debugging"""
    if frappe:
        frappe.publish_realtime("toconsole", data, user=frappe.session.user)


# Patch get_other_conditions to exclude pos_only pricing rules from non-POS documents.
try:
    from erpnext.accounts.doctype.pricing_rule import utils as pr_utils
    from pos_next.overrides.pricing_rule import patch_get_other_conditions
    patch_get_other_conditions(pr_utils)
except Exception:
    pass
