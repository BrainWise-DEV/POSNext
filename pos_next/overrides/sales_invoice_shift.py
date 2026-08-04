import frappe

def set_opening_shift(doc, method=None):
    """Auto-populate posa_pos_opening_shift on Sales Invoice if not already set."""
    if not getattr(doc, "is_pos", 0):
        return

    if getattr(doc, "posa_pos_opening_shift", None):
        return

    if not doc.pos_profile:
        return

    open_shift = frappe.db.get_value(
        "POS Opening Shift",
        {"pos_profile": doc.pos_profile, "status": "Open", "docstatus": 1},
        "name",
        order_by="period_start_date desc",
    )

    if open_shift:
        doc.posa_pos_opening_shift = open_shift