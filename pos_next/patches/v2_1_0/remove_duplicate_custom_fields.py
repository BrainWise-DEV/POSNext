# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Remove Custom Field rows that duplicate an existing (dt, fieldname).

A customization file once carried a record whose ``name`` belonged to one field
while its ``fieldname`` belonged to another:

    name      = "Pricing Rule-custom_one_time_per_customer"
    fieldname = "custom_column_break_uoqze"

``sync_customizations_for_doctype`` looks a field up by **fieldname** but inserts
it under its **name**, so on sites that synced that file an orphan row was
created holding a name it had no claim to. Every later migrate then tries to
insert the real field under the same name and dies with a DuplicateEntryError,
which aborts the whole customization sync.

The duplicate is removed with ``frappe.db.delete`` rather than ``delete_doc`` on
purpose: deleting a Custom Field document drops its database column, and the
surviving record still needs it.
"""

import frappe


def execute():
	duplicates = frappe.db.sql(
		"""
		select dt, fieldname, count(*) as total
		from `tabCustom Field`
		group by dt, fieldname
		having total > 1
		""",
		as_dict=True,
	)
	if not duplicates:
		return

	removed = 0
	for group in duplicates:
		rows = frappe.db.sql(
			"""
			select name from `tabCustom Field`
			where dt = %(dt)s and fieldname = %(fieldname)s
			order by creation asc
			""",
			group,
			as_dict=True,
		)
		names = [row["name"] for row in rows]

		# Prefer the canonically named row; Frappe also names UI-created fields
		# with a `custom_` prefix, so accept that form too. Otherwise keep the
		# oldest, which is the one the column was created for.
		canonical = f"{group['dt']}-{group['fieldname']}"
		prefixed = f"{group['dt']}-custom_{group['fieldname']}"
		keep = next((n for n in names if n in (canonical, prefixed)), names[0])

		for name in names:
			if name == keep:
				continue
			frappe.db.delete("Custom Field", {"name": name})
			removed += 1
			frappe.logger().info(
				f"Removed duplicate Custom Field {name!r} "
				f"(kept {keep!r} for {group['dt']}.{group['fieldname']})"
			)

	if removed:
		frappe.db.commit()
