# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, time_diff_in_hours, get_datetime


def execute(filters=None):
	data, payment_methods = get_data(filters)
	columns = get_columns(payment_methods)
	chart = get_chart_data(data, payment_methods)
	return columns, data, None, chart


def get_columns(payment_methods):
	"""Return columns for the report.

	Generates dynamic columns per payment method found in the data.
	"""
	columns = [
		{
			"fieldname": "shift",
			"label": _("Shift"),
			"fieldtype": "Link",
			"options": "POS Closing Shift",
			"width": 150
		},
		{
			"fieldname": "pos_profile",
			"label": _("POS Profile"),
			"fieldtype": "Link",
			"options": "POS Profile",
			"width": 150
		},
		{
			"fieldname": "cashier",
			"label": _("Cashier"),
			"fieldtype": "Link",
			"options": "User",
			"width": 150
		},
		{
			"fieldname": "posting_date",
			"label": _("Date"),
			"fieldtype": "Date",
			"width": 100
		},
		{
			"fieldname": "shift_start",
			"label": _("Shift Start"),
			"fieldtype": "Time",
			"width": 100
		},
		{
			"fieldname": "shift_end",
			"label": _("Shift End"),
			"fieldtype": "Time",
			"width": 100
		},
		{
			"fieldname": "shift_hours",
			"label": _("Shift Hours"),
			"fieldtype": "Float",
			"width": 90
		},
		{
			"fieldname": "total_transactions",
			"label": _("Transactions"),
			"fieldtype": "Int",
			"width": 100
		},
	]

	# Dynamic columns per payment method
	for method in payment_methods:
		safe = method.lower().replace(" ", "_")
		columns.extend([
			{
				"fieldname": f"{safe}_opening",
				"label": _(f"{method} Opening"),
				"fieldtype": "Currency",
				"width": 130
			},
			{
				"fieldname": f"{safe}_expected",
				"label": _(f"{method} Expected"),
				"fieldtype": "Currency",
				"width": 130
			},
			{
				"fieldname": f"{safe}_closing",
				"label": _(f"{method} Closing"),
				"fieldtype": "Currency",
				"width": 130
			},
			{
				"fieldname": f"{safe}_diff",
				"label": _(f"{method} Diff"),
				"fieldtype": "Currency",
				"width": 110
			},
		])

	columns.extend([
		{
			"fieldname": "total_opening",
			"label": _("Total Opening"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "total_expected",
			"label": _("Total Expected"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "total_closing",
			"label": _("Total Closing"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "total_difference",
			"label": _("Total Difference"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "status",
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 120
		},
	])

	return columns


def get_data(filters):
	"""Get payment reconciliation data — one row per shift."""
	conditions = get_conditions(filters)

	# Get payment reconciliation details from closing shifts
	query = """
		SELECT
			pcs.name as shift,
			pcs.pos_profile,
			pcs.user as cashier,
			DATE(pcs.period_end_date) as posting_date,
			TIME(pcs.period_start_date) as shift_start,
			TIME(pcs.period_end_date) as shift_end,
			pcs.period_start_date as _shift_start_dt,
			pcs.period_end_date as _shift_end_dt,
			pr.mode_of_payment as payment_method,
			pr.opening_amount,
			pr.expected_amount,
			pr.closing_amount,
			pr.difference
		FROM
			`tabPOS Closing Shift` pcs
		INNER JOIN
			`tabPOS Closing Shift Detail` pr ON pr.parent = pcs.name
		WHERE
			pcs.docstatus = 1
			{conditions}
		ORDER BY
			pcs.period_end_date DESC, pr.mode_of_payment
	""".format(conditions=conditions)

	raw = frappe.db.sql(query, filters, as_dict=1)

	if not raw:
		return [], []

	# Discover payment methods (ordered by first appearance)
	payment_methods = list(dict.fromkeys(r.payment_method for r in raw))

	# Batch-fetch transaction counts per shift (total, not per method)
	transaction_map = _get_transaction_counts(raw)

	# Pivot: group rows by shift into one row each
	shifts = {}
	shift_order = []
	for r in raw:
		if r.shift not in shifts:
			shift_order.append(r.shift)
			# Calculate shift hours
			if r._shift_start_dt and r._shift_end_dt:
				shift_hours = flt(time_diff_in_hours(
					get_datetime(r._shift_end_dt),
					get_datetime(r._shift_start_dt)
				), 1)
			else:
				shift_hours = 0

			shifts[r.shift] = {
				"shift": r.shift,
				"pos_profile": r.pos_profile,
				"cashier": r.cashier,
				"posting_date": r.posting_date,
				"shift_start": r.shift_start,
				"shift_end": r.shift_end,
				"shift_hours": shift_hours,
				"total_transactions": transaction_map.get(r.shift, 0),
				"total_opening": 0,
				"total_expected": 0,
				"total_closing": 0,
				"total_difference": 0,
			}

		row = shifts[r.shift]
		safe = r.payment_method.lower().replace(" ", "_")
		opening = flt(r.opening_amount, 2)
		expected = flt(r.expected_amount, 2)
		closing = flt(r.closing_amount, 2)
		diff = flt(closing - expected, 2)
		row[f"{safe}_opening"] = opening
		row[f"{safe}_expected"] = expected
		row[f"{safe}_closing"] = closing
		row[f"{safe}_diff"] = diff

		row["total_opening"] += opening
		row["total_expected"] += expected
		row["total_closing"] += closing
		row["total_difference"] += diff

	# Build final data list and determine status
	data = []
	for shift_name in shift_order:
		row = shifts[shift_name]
		row["total_opening"] = flt(row["total_opening"], 2)
		row["total_expected"] = flt(row["total_expected"], 2)
		row["total_closing"] = flt(row["total_closing"], 2)
		row["total_difference"] = flt(row["total_difference"], 2)

		# Determine status based on total difference
		abs_diff = abs(row["total_difference"])
		if abs_diff == 0:
			row["status"] = "✓ Balanced"
		elif abs_diff <= 10:
			row["status"] = "~ Minor Variance"
		elif row["total_difference"] > 0:
			row["status"] = "↑ Over"
		else:
			row["status"] = "↓ Short"

		data.append(row)

	return data, payment_methods


def _get_transaction_counts(data):
	"""Batch-fetch total transaction counts per shift.

	Counts distinct Sales Invoices in each shift.
	"""
	shift_names = list({row.shift for row in data})
	if not shift_names:
		return {}

	placeholders = ", ".join(["%s"] * len(shift_names))

	rows = frappe.db.sql("""
		SELECT
			sir.parent as shift,
			COUNT(DISTINCT sir.sales_invoice) as cnt
		FROM `tabSales Invoice Reference` sir
		WHERE sir.parenttype = 'POS Closing Shift'
		AND sir.parent IN ({placeholders})
		GROUP BY sir.parent
	""".format(placeholders=placeholders), shift_names, as_dict=1)

	return {r.shift: r.cnt for r in rows}


def get_conditions(filters):
	"""Build WHERE conditions"""
	conditions = []

	if filters.get("from_date"):
		conditions.append("pcs.period_end_date >= %(from_date)s")

	if filters.get("to_date"):
		conditions.append("pcs.period_end_date <= %(to_date)s")

	if filters.get("pos_profile"):
		conditions.append("pcs.pos_profile = %(pos_profile)s")

	if filters.get("cashier"):
		conditions.append("pcs.user = %(cashier)s")

	if filters.get("shift"):
		conditions.append("pcs.name = %(shift)s")

	if filters.get("mode_of_payment"):
		conditions.append("pr.mode_of_payment = %(mode_of_payment)s")

	return " AND " + " AND ".join(conditions) if conditions else ""


def get_chart_data(data, payment_methods):
	"""Generate chart showing opening, closing, and difference per shift."""
	if not data:
		return None

	labels = [row.get("shift") for row in data]
	opening_values = [flt(row.get("total_opening", 0), 2) for row in data]
	expected_values = [flt(row.get("total_expected", 0), 2) for row in data]
	closing_values = [flt(row.get("total_closing", 0), 2) for row in data]
	diff_values = [flt(row.get("total_difference", 0), 2) for row in data]

	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Opening"), "values": opening_values},
				{"name": _("Expected"), "values": expected_values},
				{"name": _("Closing"), "values": closing_values},
				{"name": _("Difference"), "values": diff_values},
			]
		},
		"type": "bar",
		"fieldtype": "Currency",
		"colors": ["#318AD8", "#F5A623", "#48BB74", "#F56B6B"],
	}
