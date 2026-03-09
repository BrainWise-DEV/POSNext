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
		{"fieldname": "cashier", "label": _("Cashier"), "fieldtype": "Link", "options": "User", "width": 180},
		{"fieldname": "cashier_name", "label": _("Cashier Name"), "fieldtype": "Data", "width": 150},
		{"fieldname": "total_sales", "label": _("Total Sales"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "invoice_count", "label": _("Invoices"), "fieldtype": "Int", "width": 90},
		{"fieldname": "average_invoice_value", "label": _("Avg Invoice Value"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "total_discounts", "label": _("Discounts Given"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "discount_percentage", "label": _("Discount %"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "return_count", "label": _("Returns"), "fieldtype": "Int", "width": 90},
		{"fieldname": "return_amount", "label": _("Return Amount"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "return_percentage", "label": _("Return %"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "net_sales", "label": _("Net Sales"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "shifts_worked", "label": _("Shifts Worked"), "fieldtype": "Int", "width": 110},
		{"fieldname": "avg_sales_per_shift", "label": _("Avg Sales/Shift"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "performance_rating", "label": _("Performance Rating"), "fieldtype": "Data", "width": 140}
	]


def get_data(filters):
	"""Get cashier performance data.

	Uses two separate queries to avoid cartesian-product inflation:
	1. Invoice aggregates grouped by cashier (owner)
	2. Shift count from POS Closing Shift via Sales Invoice Reference
	"""
	conditions = get_conditions(filters)

	# Query 1: Invoice aggregates — no JOIN to shifts, so no duplication
	query = """
		SELECT
			si.owner as cashier,
			COALESCE(SUM(CASE WHEN si.is_return = 0 THEN si.grand_total ELSE 0 END), 0) as total_sales,
			COUNT(CASE WHEN si.is_return = 0 THEN si.name END) as invoice_count,
			COALESCE(SUM(CASE WHEN si.is_return = 0 THEN si.discount_amount ELSE 0 END), 0) as total_discounts,
			COUNT(CASE WHEN si.is_return = 1 THEN si.name END) as return_count,
			COALESCE(SUM(CASE WHEN si.is_return = 1 THEN ABS(si.grand_total) ELSE 0 END), 0) as return_amount
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		AND si.is_pos = 1
		{conditions}
		GROUP BY si.owner
		ORDER BY total_sales DESC
	""".format(conditions=conditions)

	data = frappe.db.sql(query, filters, as_dict=1)

	# Query 2: Shifts worked per cashier via Sales Invoice Reference
	# Count distinct closing shifts that contain at least one invoice owned by this cashier
	shift_conditions = _build_shift_conditions(filters)
	shift_query = """
		SELECT
			pcs.user as cashier,
			COUNT(DISTINCT pcs.name) as shifts_worked
		FROM `tabPOS Closing Shift` pcs
		WHERE pcs.docstatus = 1
		{conditions}
		GROUP BY pcs.user
	""".format(conditions=shift_conditions)

	shift_data = frappe.db.sql(shift_query, filters, as_dict=1)
	shift_map = {row.cashier: row.shifts_worked for row in shift_data}

	# Get cashier names and calculate derived metrics
	for row in data:
		row.shifts_worked = shift_map.get(row.cashier, 0)
		row.cashier_name = frappe.db.get_value("User", row.cashier, "full_name")

		# Calculate derived metrics
		if row.invoice_count > 0:
			row.average_invoice_value = flt(row.total_sales / row.invoice_count, 2)
		else:
			row.average_invoice_value = 0

		if row.total_sales > 0:
			row.discount_percentage = flt((row.total_discounts / row.total_sales) * 100, 2)
			row.return_percentage = flt((row.return_amount / row.total_sales) * 100, 2)
		else:
			row.discount_percentage = 0
			row.return_percentage = 0

		row.net_sales = flt(row.total_sales - row.return_amount, 2)

		if row.shifts_worked > 0:
			row.avg_sales_per_shift = flt(row.total_sales / row.shifts_worked, 2)
		else:
			row.avg_sales_per_shift = 0

		# Performance rating
		rating_score = 0

		# Factor 1: Sales volume (30%)
		if row.total_sales >= 100000:
			rating_score += 30
		elif row.total_sales >= 50000:
			rating_score += 20
		elif row.total_sales >= 25000:
			rating_score += 10

		# Factor 2: Invoice count (20%)
		if row.invoice_count >= 100:
			rating_score += 20
		elif row.invoice_count >= 50:
			rating_score += 15
		elif row.invoice_count >= 25:
			rating_score += 10

		# Factor 3: Low return rate (25%)
		if row.return_percentage <= 5:
			rating_score += 25
		elif row.return_percentage <= 10:
			rating_score += 15
		elif row.return_percentage <= 15:
			rating_score += 10

		# Factor 4: Reasonable discount rate (25%)
		if row.discount_percentage <= 10:
			rating_score += 25
		elif row.discount_percentage <= 15:
			rating_score += 15
		elif row.discount_percentage <= 20:
			rating_score += 10

		# Assign rating
		if rating_score >= 80:
			row.performance_rating = "⭐ Excellent"
		elif rating_score >= 60:
			row.performance_rating = "✓ Good"
		elif rating_score >= 40:
			row.performance_rating = "○ Average"
		else:
			row.performance_rating = "△ Needs Improvement"

	return data


def get_conditions(filters):
	"""Build WHERE conditions for the invoice query"""
	conditions = []

	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")

	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")

	if filters.get("pos_profile"):
		conditions.append("si.pos_profile = %(pos_profile)s")

	if filters.get("cashier"):
		conditions.append("si.owner = %(cashier)s")

	if filters.get("shift"):
		conditions.append("""
			EXISTS (
				SELECT 1 FROM `tabSales Invoice Reference` sir
				WHERE sir.sales_invoice = si.name
				AND sir.parent = %(shift)s
				AND sir.parenttype = 'POS Closing Shift'
			)
		""")

	return "AND " + " AND ".join(conditions) if conditions else ""


def _build_shift_conditions(filters):
	"""Build WHERE conditions for the shift count query"""
	conditions = []

	if filters.get("from_date"):
		conditions.append("pcs.period_start_date >= %(from_date)s")

	if filters.get("to_date"):
		conditions.append("pcs.period_end_date <= %(to_date)s")

	if filters.get("pos_profile"):
		conditions.append("pcs.pos_profile = %(pos_profile)s")

	if filters.get("cashier"):
		conditions.append("pcs.user = %(cashier)s")

	if filters.get("shift"):
		conditions.append("pcs.name = %(shift)s")

	return "AND " + " AND ".join(conditions) if conditions else ""


def get_chart_data(data):
	"""Generate chart for top performers"""
	if not data:
		return None

	# Top 10 cashiers by sales
	top_cashiers = data[:10]

	return {
		"data": {
			"labels": [row.get("cashier_name") or row.get("cashier") for row in top_cashiers],
			"datasets": [{"name": "Total Sales", "values": [row.total_sales for row in top_cashiers]}]
		},
		"type": "bar",
		"colors": ["#4CAF50"]
	}
