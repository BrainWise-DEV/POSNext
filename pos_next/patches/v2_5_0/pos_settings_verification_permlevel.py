# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Make the POS Settings "Customer Verification" permlevel take effect.

Any Custom DocPerm row for a DocType replaces all of its DocType permissions.
Sites installed before the POS Settings permissions moved into the DocType
(commit 6a79636c) can still carry Custom DocPerm rows for it, so the new
permlevel-1 rows in the DocType would be ignored there.

* The Custom DocPerm set is exactly the DocType's level-0 rows (same roles,
  same flags): it is redundant, so it is deleted and the DocType permissions
  (with their level-1 rows) apply. Nobody gains or loses access.
* Anything else is a site customisation and is kept. The DocType's level-1
  rows are added only for roles that already have level-0 read in the custom
  set, so no role gains access it did not have.

Roles come from permission rows (data), never from a list in code.
"""

import frappe

DOCTYPE = "POS Settings"

PERM_FLAGS = (
	"if_owner",
	"select",
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"report",
	"export",
	"import",
	"share",
	"print",
	"email",
)


def _rows(doctype_name):
	table = frappe.qb.DocType(doctype_name)
	return (
		frappe.qb.from_(table)
		.select(table.name, table.role, table.permlevel, *[table[f] for f in PERM_FLAGS])
		.where(table.parent == DOCTYPE)
		.run(as_dict=True)
	)


def _level(row):
	return int(row.get("permlevel") or 0)


def _signature(row):
	return (row.role, _level(row), tuple(int(row.get(f) or 0) for f in PERM_FLAGS))


def plan(custom, standard):
	"""Return ``(names_to_delete, rows_to_add)`` for the Custom DocPerm set."""
	if not custom:
		return [], []
	level0 = [r for r in standard if _level(r) == 0]
	if sorted(map(_signature, custom)) == sorted(map(_signature, level0)):
		return [r.name for r in custom], []

	readers = {r.role for r in custom if _level(r) == 0 and int(r.get("read") or 0)}
	have_level_1 = {r.role for r in custom if _level(r) == 1}
	to_add = [
		{"role": r.role, "permlevel": 1, **{f: int(r.get(f) or 0) for f in PERM_FLAGS}}
		for r in standard
		if _level(r) == 1 and r.role in readers and r.role not in have_level_1
	]
	return [], to_add


def execute():
	to_delete, to_add = plan(_rows("Custom DocPerm"), _rows("DocPerm"))
	for name in to_delete:
		frappe.delete_doc("Custom DocPerm", name, ignore_permissions=True, force=True)
	for row in to_add:
		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": DOCTYPE,
				"parenttype": "DocType",
				"parentfield": "permissions",
				**row,
			}
		).insert(ignore_permissions=True)
	if to_delete or to_add:
		frappe.clear_cache(doctype=DOCTYPE)
