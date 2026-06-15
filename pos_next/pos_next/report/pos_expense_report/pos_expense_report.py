# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"fieldname": "journal_entry",
			"label": _("Journal Entry"),
			"fieldtype": "Link",
			"options": "Journal Entry",
			"width": 150,
		},
		{
			"fieldname": "posting_date",
			"label": _("Posting Date"),
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"fieldname": "company",
			"label": _("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"width": 140,
		},
		{
			"fieldname": "pos_opening_shift",
			"label": _("POS Opening Shift"),
			"fieldtype": "Link",
			"options": "POS Opening Shift",
			"width": 160,
		},
		{
			"fieldname": "pos_profile",
			"label": _("POS Profile"),
			"fieldtype": "Link",
			"options": "POS Profile",
			"width": 140,
		},
		{
			"fieldname": "expense_account",
			"label": _("Expense Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 180,
		},
		{
			"fieldname": "amount",
			"label": _("Amount"),
			"fieldtype": "Currency",
			"width": 120,
		},
		{
			"fieldname": "mode_of_payment",
			"label": _("Mode of Payment"),
			"fieldtype": "Link",
			"options": "Mode of Payment",
			"width": 140,
		},
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 140,
		},
		{
			"fieldname": "remarks",
			"label": _("Remarks"),
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"fieldname": "created_by",
			"label": _("Created By"),
			"fieldtype": "Link",
			"options": "User",
			"width": 140,
		},
	]


def get_data(filters):
	filters = filters or {}
	conditions = ["je.posa_is_pos_expense = 1", "je.docstatus = 1"]
	values = {}

	if filters.get("company"):
		conditions.append("je.company = %(company)s")
		values["company"] = filters["company"]

	if filters.get("from_date"):
		conditions.append("je.posting_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("je.posting_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	if filters.get("pos_profile"):
		conditions.append("je.posa_pos_profile = %(pos_profile)s")
		values["pos_profile"] = filters["pos_profile"]

	if filters.get("pos_opening_shift"):
		conditions.append("je.posa_pos_opening_shift = %(pos_opening_shift)s")
		values["pos_opening_shift"] = filters["pos_opening_shift"]

	if filters.get("mode_of_payment"):
		conditions.append("je.posa_expense_mode_of_payment = %(mode_of_payment)s")
		values["mode_of_payment"] = filters["mode_of_payment"]

	if filters.get("employee"):
		conditions.append("je.posa_expense_employee = %(employee)s")
		values["employee"] = filters["employee"]

	rows = frappe.db.sql(
		f"""
		SELECT
			je.name AS journal_entry,
			je.posting_date,
			je.company,
			je.posa_pos_opening_shift AS pos_opening_shift,
			je.posa_pos_profile AS pos_profile,
			je.posa_expense_account AS expense_account,
			je.posa_expense_amount AS amount,
			je.posa_expense_mode_of_payment AS mode_of_payment,
			je.posa_expense_employee AS employee,
			je.user_remark AS remarks,
			je.owner AS created_by
		FROM `tabJournal Entry` je
		WHERE {" AND ".join(conditions)}
		ORDER BY je.posting_date DESC, je.creation DESC
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		row.amount = flt(row.amount)

	return rows
