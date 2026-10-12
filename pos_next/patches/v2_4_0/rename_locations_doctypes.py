# Copyright (c) 2026, BrainWise and contributors

"""Migrate pos_next Governorate and District records to POS Governorate and POS District.

Resolves naming conflicts with third-party apps by moving pos_next data to new DocTypes 
while preserving shared rows. Customer links remain valid, unused legacy tables are 
cleaned up, and the migration is fully idempotent.
"""

import frappe

MOVES = (
    ("Governorate", "POS Governorate", "governorate", "governorate_en", ()),
    ("District", "POS District", "district", "district_en", ("governorate",)),
)
CUSTOM_FIELDS = (
    ("custom_governorate", "Governorate", "POS Governorate"),
    ("custom_district", "District", "POS District"),
)
COMMON = ("name", "creation", "modified", "modified_by", "owner", "docstatus", "idx")


def execute():
    moved = {}
    for old, new, label, other, extra in MOVES:
        moved[old] = _copy_rows(old, new, label, other, extra)

    # Use frappe.db.set_value to update Custom Fields via Frappe API
    for fieldname, old, new in CUSTOM_FIELDS:
        custom_field = frappe.db.get_value(
            "Custom Field",
            {"dt": "Customer", "fieldname": fieldname, "options": old},
            "name",
        )
        if custom_field:
            frappe.db.set_value("Custom Field", custom_field, "options", new)

    # District links to Governorate, so it has to go first.
    for old, new, label, other, _extra in reversed(MOVES):
        _retire_old_doctype(old, new, label, other, moved[old])

    frappe.clear_cache(doctype="Customer")


def _pos_next_rows(old, label, other):
    """WHERE clause selecting the rows pos_next created in the old table."""
    where = f"ifnull(`{label}`, '') != ''"
    if frappe.db.has_column(old, other):
        where += f" and ifnull(`{other}`, '') = ''"
    return where


def _copy_rows(old, new, label, other, extra):
    if not frappe.db.table_exists(old) or not frappe.db.has_column(old, label):
        return 0
    if not frappe.db.table_exists(new):
        frappe.throw(f"{new} has not been migrated yet")

    columns = ", ".join(f"`{c}`" for c in (*COMMON, label, *extra))
    where_clause = _pos_next_rows(old, label, other)

    frappe.db.sql(
        f"insert ignore into `tab{new}` ({columns}) "
        f"select {columns} from `tab{old}` where {where_clause}"
    )

    return frappe.db.sql(
        f"select count(*) from `tab{old}` where {where_clause}"
    )[0][0]


def _retire_old_doctype(old, new, label, other, copied):
    if not frappe.db.table_exists(old) or not frappe.db.has_column(old, label):
        return

    if frappe.db.has_column(old, other):
        # Another app's rows share this table. Drop only the rows that were copied.
        # Temp derived table solves MySQL Error 1093 on DELETE subquery
        where_clause = _pos_next_rows(old, label, other)
        frappe.db.sql(
            f"delete from `tab{old}` where {where_clause} "
            f"and name in (select name from (select name from `tab{new}`) as _temp)"
        )
        frappe.logger().info(
            f"{old}: kept for another app; reload its DocType with `bench reload-doc` if its fields are missing"
        )
        return

    remaining = frappe.db.count(old)
    copied_names = frappe.db.count(new)
    if remaining > copied_names:
        frappe.logger().warning(
            f"{old}: {remaining} rows but only {copied_names} copied; not removing"
        )
        return

    if _other_references(old):
        return

    if frappe.db.exists("DocType", old):
        frappe.delete_doc("DocType", old, force=True, ignore_missing=True)

    frappe.db.sql_ddl(f"drop table if exists `tab{old}`")


def _other_references(doctype):
    """True when a field of another DocType still links to ``doctype``."""
    linked = frappe.db.get_all(
        "DocField",
        filters={"fieldtype": ["in", ["Link", "Table MultiSelect"]], "options": doctype},
        or_filters={"parent": ["!=", doctype]},
        pluck="parent",
    )
    custom = frappe.db.get_all(
        "Custom Field",
        filters={"fieldtype": "Link", "options": doctype},
        pluck="dt",
    )
    return bool(linked or custom)