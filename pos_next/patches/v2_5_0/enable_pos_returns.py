# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Keep POS returns on for every existing POS Settings row (D-R3-10).

POS Settings "Allow Return" was read nowhere, so POS returns worked whatever it
said, and it defaulted to 0. The server now refuses returns while it is off, so
every row that exists when this runs is set to 1: no site loses returns on
upgrade. New rows default to 1 (the field's default). Rows already at 1 are left
as they are, so running it again changes nothing.
"""

import frappe

DOCTYPE = "POS Settings"


def execute():
	if not frappe.db.has_column(DOCTYPE, "allow_return"):
		return
	settings = frappe.qb.DocType(DOCTYPE)
	(
		frappe.qb.update(settings)
		.set(settings.allow_return, 1)
		.where((settings.allow_return != 1) | settings.allow_return.isnull())
	).run()
