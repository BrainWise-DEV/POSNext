# -*- coding: utf-8 -*-
# API module for POS Next

import frappe

# Import API modules to make them accessible
from . import invoices
from . import items
from . import shifts
from . import pos_profile
from . import customers
from . import offers
from . import promotions
from . import utilities
from . import gst_tax
from . import tax_utils

@frappe.whitelist(allow_guest=True)
def ping():
    """Simple ping endpoint for connectivity checks"""
    return "pong"
