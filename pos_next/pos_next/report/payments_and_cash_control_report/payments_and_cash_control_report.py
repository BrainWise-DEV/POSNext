# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart_data(data)
	return columns, data, None, chart


def get_columns():
	"""Return columns for the report"""
	return [
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
			"fieldname": "payment_method",
			"label": _("Payment Method"),
			"fieldtype": "Data",
			"width": 130
		},
		{
			"fieldname": "expected_amount",
			"label": _("Expected Amount"),
			"fieldtype": "Currency",
			"width": 140
		},
		{
			"fieldname": "actual_amount",
			"label": _("Actual Amount"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "difference",
			"label": _("Difference"),
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"fieldname": "variance_percentage",
			"label": _("Variance %"),
			"fieldtype": "Percent",
			"width": 100
		},
		{
			"fieldname": "status",
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "transaction_count",
			"label": _("Transactions"),
			"fieldtype": "Int",
			"width": 110
		}
	]


def get_data(filters):
	"""Get payment reconciliation data"""
	conditions = get_conditions(filters)

	# Get payment reconciliation details from closing shifts
	query = f"""
		SELECT
			pcs.name as shift,
			pcs.pos_profile,
			pcs.user as cashier,
			DATE(pcs.period_end_date) as posting_date,
			pr.mode_of_payment as payment_method,
			pr.expected_amount,
			pr.closing_amount as actual_amount,
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
	"""

	data = frappe.db.sql(query, filters, as_dict=1)

	# Calculate variance and status for each payment method
	for row in data:
		# Calculate variance percentage
		if row.expected_amount > 0:
			row.variance_percentage = flt((row.difference / row.expected_amount) * 100, 2)
		else:
			row.variance_percentage = 0

		# Determine status
		abs_difference = abs(row.difference)
		if abs_difference == 0:
			row.status = "✓ Balanced"
		elif abs_difference <= 10:  # Within 10 currency units
			row.status = "~ Minor Variance"
		elif row.difference > 0:
			row.status = "↑ Over"
		else:
			row.status = "↓ Short"

		# Get transaction count for this payment method in this shift
		row.transaction_count = frappe.db.count(
			"Sales Invoice Payment",
			filters={
				"parenttype": "Sales Invoice",
				"mode_of_payment": row.payment_method,
				"parent": ["in", frappe.get_all(
					"Sales Invoice",
					filters={
						"pos_profile": row.pos_profile,
						"owner": row.cashier,
						"posting_date": row.posting_date,
						"docstatus": 1,
						"is_pos": 1
					},
					pluck="name"
				)]
			}
		)

	return data


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

	return " AND " + " AND ".join(conditions) if conditions else ""


def get_chart_data(data):
	"""Generate chart showing payment method breakdown"""
	if not data:
		return None

	# Aggregate by payment method
	payment_summary = {}
	for row in data:
		method = row.payment_method
		if method not in payment_summary:
			payment_summary[method] = 0
		payment_summary[method] += row.expected_amount

	return {
		"data": {
			"labels": list(payment_summary.keys()),
			"datasets": [
				{
					"name": "Total Amount",
					"values": list(payment_summary.values())
				}
			]
		},
		"type": "pie"
	}
