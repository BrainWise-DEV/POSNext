# -*- coding: utf-8 -*-
from __future__ import unicode_literals

try:
    import frappe
except ModuleNotFoundError:  # pragma: no cover - frappe may not be installed during setup
    frappe = None

__version__ = "1.13.0"


def console(*data):
    """Publish data to browser console for debugging"""
    if frappe:
        frappe.publish_realtime("toconsole", data, user=frappe.session.user)
