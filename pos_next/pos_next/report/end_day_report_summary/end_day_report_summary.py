# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	"""Return a simple and readable column list for a daily end summary."""
	return [
		{
			"fieldname": "posting_date",
			"label": _("Posting Date"),
			"fieldtype": "Date",
			"width": 110
		},
		{
			"fieldname": "cashier",
			"label": _("Cashier"),
			"fieldtype": "Link",
			"options": "User",
			"width": 140
		},
		{
			"fieldname": "cashier_name",
			"label": _("Cashier Name"),
			"fieldtype": "Data",
			"width": 160
		},
		{
			"fieldname": "total_bills",
			"label": _("Total Bills"),
			"fieldtype": "Int",
			"width": 100
		},
		{
			"fieldname": "return_bills",
			"label": _("Return Bills"),
			"fieldtype": "Int",
			"width": 110
		},
		{
			"fieldname": "gross_sales",
			"label": _("Gross Sales"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "discounts",
			"label": _("Discounts"),
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"fieldname": "returns",
			"label": _("Returns"),
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"fieldname": "refunds",
			"label": _("Refunds"),
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"fieldname": "net_sales",
			"label": _("Net Sales"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "cash",
			"label": _("Cash"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "card",
			"label": _("Card"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "wallet",
			"label": _("Wallet / UPI"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "payment_total",
			"label": _("Payment Total"),
			"fieldtype": "Currency",
			"width": 130
		},
	]


def get_data(filters):
	"""Return a readable daily summary row per cashier."""
	conditions = build_conditions(filters)

	daily_query = """
		SELECT
			DATE(pcs.posting_date) AS posting_date,
			pcs.user AS cashier,
			COALESCE(SUM(CASE WHEN si.is_return = 0 THEN si.grand_total ELSE 0 END), 0) AS gross_sales,
			COALESCE(SUM(CASE WHEN si.is_return = 0 THEN si.discount_amount ELSE 0 END), 0) AS discounts,
			COALESCE(SUM(CASE WHEN si.is_return = 1 THEN ABS(si.grand_total) ELSE 0 END), 0) AS returns,
			COUNT(CASE WHEN si.is_return = 0 THEN si.name END) AS total_bills,
			COUNT(CASE WHEN si.is_return = 1 THEN si.name END) AS return_bills
		FROM `tabPOS Closing Shift` pcs
		LEFT JOIN `tabSales Invoice Reference` sir ON sir.parent = pcs.name
			AND sir.parenttype = 'POS Closing Shift'
		LEFT JOIN `tabSales Invoice` si ON si.name = sir.sales_invoice
			AND si.docstatus = 1
		WHERE pcs.docstatus = 1
		{conditions}
		GROUP BY DATE(pcs.posting_date), pcs.user
		ORDER BY posting_date DESC, cashier
	""".format(conditions=conditions)

	daily_rows = frappe.db.sql(daily_query, filters, as_dict=True)
	if not daily_rows:
		return []

	payment_rows = get_payment_summary(filters)
	refund_rows = get_refund_summary(filters)

	payment_map = {}
	for row in payment_rows:
		payment_map[(row.posting_date, row.cashier)] = {
			"cash": flt(row.cash, 2),
			"card": flt(row.card, 2),
			"wallet": flt(row.wallet, 2),
			"payment_total": flt(row.payment_total, 2),
		}

	refund_map = {}
	for row in refund_rows:
		refund_map[(row.posting_date, row.cashier)] = flt(row.refunds, 2)

	cashier_ids = [row.cashier for row in daily_rows]
	cashier_names = get_cashier_names(cashier_ids)

	data = []
	for row in daily_rows:
		row.cashier_name = cashier_names.get(row.cashier, row.cashier)
		row.returns = flt(row.returns, 2)
		row.discounts = flt(row.discounts, 2)
		row.gross_sales = flt(row.gross_sales, 2)
		row.net_sales = flt(row.gross_sales - row.returns, 2)
		row.total_bills = int(row.total_bills or 0)
		row.return_bills = int(row.return_bills or 0)
		row.refunds = flt(refund_map.get((row.posting_date, row.cashier), 0), 2)

		mode_totals = payment_map.get((row.posting_date, row.cashier), {})
		row.cash = flt(mode_totals.get("cash", 0), 2)
		row.card = flt(mode_totals.get("card", 0), 2)
		row.wallet = flt(mode_totals.get("wallet", 0), 2)
		row.payment_total = flt(mode_totals.get("payment_total", 0), 2)
		data.append(row)

	return data


def build_conditions(filters):
	"""Build simple SQL conditions from the report filters."""
	conditions = []

	if filters.get("from_date"):
		conditions.append("pcs.posting_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("pcs.posting_date <= %(to_date)s")
	if filters.get("pos_profile"):
		conditions.append("pcs.pos_profile = %(pos_profile)s")
	if filters.get("cashier"):
		conditions.append("pcs.user = %(cashier)s")
	if filters.get("shift"):
		conditions.append("pcs.name = %(shift)s")

	return "AND " + " AND ".join(conditions) if conditions else ""


def get_payment_summary(filters):
	"""Return payment totals grouped by posting date and cashier."""
	conditions = build_conditions(filters)

	query = """
		SELECT
			DATE(pcs.posting_date) AS posting_date,
			pcs.user AS cashier,
			COALESCE(SUM(CASE WHEN LOWER(pr.mode_of_payment) LIKE '%%cash%%' THEN CASE WHEN COALESCE(pr.closing_amount, 0) > 0 THEN pr.closing_amount ELSE pr.expected_amount END ELSE 0 END), 0) AS cash,
			COALESCE(SUM(CASE WHEN LOWER(pr.mode_of_payment) LIKE '%%card%%' OR LOWER(pr.mode_of_payment) LIKE '%%credit%%' OR LOWER(pr.mode_of_payment) LIKE '%%debit%%' THEN CASE WHEN COALESCE(pr.closing_amount, 0) > 0 THEN pr.closing_amount ELSE pr.expected_amount END ELSE 0 END), 0) AS card,
			COALESCE(SUM(CASE WHEN LOWER(pr.mode_of_payment) LIKE '%%upi%%' OR LOWER(pr.mode_of_payment) LIKE '%%wallet%%' OR LOWER(pr.mode_of_payment) LIKE '%%phonepe%%' OR LOWER(pr.mode_of_payment) LIKE '%%gpay%%' OR LOWER(pr.mode_of_payment) LIKE '%%paytm%%' THEN CASE WHEN COALESCE(pr.closing_amount, 0) > 0 THEN pr.closing_amount ELSE pr.expected_amount END ELSE 0 END), 0) AS wallet,
			COALESCE(SUM(CASE WHEN COALESCE(pr.closing_amount, 0) > 0 THEN pr.closing_amount ELSE pr.expected_amount END), 0) AS payment_total
		FROM `tabPOS Closing Shift Detail` pr
		INNER JOIN `tabPOS Closing Shift` pcs ON pcs.name = pr.parent
		WHERE pcs.docstatus = 1
		{conditions}
		GROUP BY DATE(pcs.posting_date), pcs.user
	""".format(conditions=conditions)

	return frappe.db.sql(query, filters, as_dict=True)


def get_refund_summary(filters):
	"""Return refund totals grouped by posting date and cashier."""
	conditions = build_conditions(filters)

	query = """
		SELECT
			DATE(pcs.posting_date) AS posting_date,
			pcs.user AS cashier,
			SUM(ABS(sip.amount)) AS refunds
		FROM `tabSales Invoice Payment` sip
		INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
		INNER JOIN `tabSales Invoice Reference` sir ON sir.sales_invoice = si.name
			AND sir.parenttype = 'POS Closing Shift'
		INNER JOIN `tabPOS Closing Shift` pcs ON pcs.name = sir.parent
		WHERE si.docstatus = 1
		AND si.is_return = 1
		{conditions}
		GROUP BY DATE(pcs.posting_date), pcs.user
	""".format(conditions=conditions)

	return frappe.db.sql(query, filters, as_dict=True)


def get_cashier_names(cashier_ids):
	"""Fetch full names for cashiers in one call."""
	if not cashier_ids:
		return {}

	users = frappe.get_all(
		"User",
		filters={"name": ["in", list(set(cashier_ids))]},
		fields=["name", "full_name"],
	)
	return {user.name: user.full_name or user.name for user in users}


def execute_snapshot_report(filters: dict | None = None):
	"""Optional snapshot-report entry point kept simple for compatibility."""
	return execute(filters)
