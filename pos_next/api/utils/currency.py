
import frappe
from frappe.utils import flt

# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

def get_base_value(doc, fieldname, base_fieldname=None, conversion_rate=None):
    """Return the value for a field in company currency."""

    base_fieldname = base_fieldname or f"base_{fieldname}"
    base_value = doc.get(base_fieldname)

    if base_value not in (None, ""):
        return flt(base_value)

    value = doc.get(fieldname)
    if value in (None, ""):
        return 0

    if conversion_rate is None:
        conversion_rate = (
            doc.get("conversion_rate")
            or doc.get("exchange_rate")
            or doc.get("target_exchange_rate")
            or doc.get("plc_conversion_rate")
            or 1
        )

    return flt(value) * flt(conversion_rate or 1)
