from __future__ import unicode_literals
import frappe
from frappe import _
from pos_next.api.utilities import check_user_company
from pos_next.api.utilities import _parse_list_parameter

@frappe.whitelist()
def get_tables(branch=None):
    filters = {}
    if branch:
        filters["branch"] = branch

    return frappe.get_all(
        "URY Table",
        fields=["name","no_of_seats", "status"],
        filters=filters,
        order_by="name asc"
    )