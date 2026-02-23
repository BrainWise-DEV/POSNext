# -*- coding: utf-8 -*-
# API module for POS Next

import frappe

# Import API modules to make them accessible
from . import auth, customers, invoices, items, offers, pos_profile, promotions, shifts, utilities


@frappe.whitelist(allow_guest=True)
def ping():
    """Simple ping endpoint for connectivity checks"""
    return "pong"
