# -*- coding: utf-8 -*-
# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import json
import frappe
from frappe import _
from frappe.utils import nowdate, nowtime, get_datetime, flt, cint
from pos_next.api.utilities import get_wallet_payment_modes


@frappe.whitelist()
def get_opening_dialog_data():
	"""Get data required for opening shift dialog"""
	data = {}

	# Get POS Profiles where current user is defined in POS Profile User table
	pos_profiles_data = frappe.db.sql(
		"""
		SELECT DISTINCT p.name, p.company, p.currency, p.warehouse, p.selling_price_list
		FROM `tabPOS Profile` p
		INNER JOIN `tabPOS Profile User` u ON u.parent = p.name
		WHERE p.disabled = 0 AND u.user = %s
		ORDER BY p.name
		""",
		frappe.session.user,
		as_dict=1,
	)

	data["pos_profiles_data"] = pos_profiles_data

	# Derive companies from accessible POS Profiles
	company_names = []
	for profile in pos_profiles_data:
		if profile.company and profile.company not in company_names:
			company_names.append(profile.company)
	data["companies"] = [{"name": c} for c in company_names]

	# Get payment methods for POS profiles (exclude wallet payment methods)
	pos_profiles_list = [p.name for p in pos_profiles_data]

	if pos_profiles_list:
		# Exclude wallet payment modes from opening balance
		wallet_modes = get_wallet_payment_modes()

		payment_filters = {"parent": ["in", pos_profiles_list]}
		if wallet_modes:
			payment_filters["mode_of_payment"] = ["not in", wallet_modes]

		data["payments_method"] = frappe.get_list(
			"POS Payment Method",
			filters=payment_filters,
			fields=["*"],
			limit_page_length=0,
			order_by="parent",
			ignore_permissions=True,
		)

		# Set currency from pos profile
		for mode in data["payments_method"]:
			mode["currency"] = frappe.get_cached_value("POS Profile", mode["parent"], "currency")
	else:
		data["payments_method"] = []

	return data


@frappe.whitelist()
def check_opening_shift(user=None):
	"""Check if user has an open shift"""
	if not user:
		user = frappe.session.user

	open_shifts = frappe.db.get_all(
		"POS Opening Shift",
		filters={
			"user": user,
			"pos_closing_shift": ["is", "not set"],
			"docstatus": 1,
			"status": "Open",
		},
		fields=["name", "pos_profile", "period_start_date"],
		order_by="period_start_date desc",
	)

	if not open_shifts:
		return None

	# Get the latest open shift
	shift_data = open_shifts[0]
	data = {}
	data["pos_opening_shift"] = frappe.get_doc("POS Opening Shift", shift_data["name"])
	data["pos_profile"] = frappe.get_doc("POS Profile", shift_data["pos_profile"])
	data["company"] = frappe.get_doc("Company", data["pos_profile"].company)
	# Include server timestamp so frontend can compute shift duration
	# without timezone mismatch (period_start_date is in server timezone)
	data["server_now"] = str(get_datetime())

	return data


@frappe.whitelist()
def create_opening_shift(pos_profile, company, balance_details):
	"""Create a new POS Opening Shift"""
	balance_details = json.loads(balance_details) if isinstance(balance_details, str) else balance_details

	# Check if user already has an open shift
	existing_shift = check_opening_shift(frappe.session.user)
	if existing_shift:
		frappe.throw(_("You already have an open shift: {0}").format(existing_shift["pos_opening_shift"].name))

	new_pos_opening = frappe.get_doc(
		{
			"doctype": "POS Opening Shift",
			"period_start_date": get_datetime(),
			"posting_date": nowdate(),
			"posting_time": nowtime(),
			"user": frappe.session.user,
			"pos_profile": pos_profile,
			"company": company,
			"status": "Open",
		}
	)

	# Add balance details - map opening_amount to amount
	formatted_balance_details = []
	for detail in balance_details:
		formatted_balance_details.append({
			"mode_of_payment": detail.get("mode_of_payment"),
			"amount": detail.get("opening_amount", 0)
		})

	new_pos_opening.set("balance_details", formatted_balance_details)
	new_pos_opening.insert(ignore_permissions=True)
	new_pos_opening.submit()

	data = {}
	data["pos_opening_shift"] = new_pos_opening.as_dict()
	data["pos_profile"] = frappe.get_doc("POS Profile", pos_profile)
	data["company"] = frappe.get_doc("Company", company)

	return data


@frappe.whitelist()
def get_closing_shift_data(opening_shift):
	"""Get data for closing shift"""
	from pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift import make_closing_shift_from_opening

	try:
		# Get the opening shift document
		opening_shift_doc = frappe.get_doc("POS Opening Shift", opening_shift)

		# Convert to dict with proper datetime serialization
		opening_shift_dict = opening_shift_doc.as_dict()
		opening_shift_json = json.dumps(opening_shift_dict, default=str)

		# Create closing shift from opening shift (returns a dict)
		closing_data = make_closing_shift_from_opening(opening_shift_json)

		# Ensure datetime values are JSON serializable
		return json.loads(json.dumps(closing_data, default=str))
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Closing Shift Data Error")
		frappe.throw(_("Error getting closing shift data: {0}").format(str(e)))


@frappe.whitelist()
def submit_closing_shift(closing_shift):
	"""Submit closing shift"""
	from pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift import submit_closing_shift as submit_shift

	try:
		# closing_shift is already a JSON string from frontend
		# If it's a dict, convert to JSON string
		if isinstance(closing_shift, dict):
			closing_shift = json.dumps(closing_shift)

		result = submit_shift(closing_shift)
		return {"name": result, "status": "success"}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Submit Closing Shift Error")
		frappe.throw(_("Error submitting closing shift: {0}").format(str(e)))


@frappe.whitelist()
def get_shift_history(filters=None, limit=25, offset=0, pos_profile=None):
	"""Return paginated shift history for the current session user only.

	Args:
		filters: JSON string or dict with optional from_date / to_date.
		limit:   Page size (default 25, max 100).
		offset:  Number of records to skip (0-based, for page navigation).

	Returns:
		{
		  "rows":   [...],          # Current page rows
		  "totals": {               # Aggregates across ALL matching rows (no page cap)
		      "total_shifts":   int,
		      "total_sales":    float,
		      "total_cash_diff": float,
		  }
		}

	Security: The session user restriction is always enforced server-side.
	Clients cannot override it by passing filters.
	"""
	if not frappe.has_permission("POS Opening Shift", "read"):
		frappe.throw(_("Insufficient permissions to view shift history"))

	if isinstance(filters, str):
		filters = json.loads(filters)

	# Clamp page size: minimum 1, maximum 100
	page_size   = max(1, min(cint(limit) or 25, 100))
	page_offset = max(0, cint(offset) or 0)

	# Mandatory WHERE conditions — user is always enforced server-side
	conditions = [
		"os.docstatus = 1",
		"os.user = %(session_user)s",
	]
	values = {
		"session_user": frappe.session.user,
		"limit":        page_size,
		"offset":       page_offset,
	}

	if filters:
		if filters.get("from_date"):
			conditions.append("os.posting_date >= %(from_date)s")
			values["from_date"] = filters["from_date"]

		if filters.get("to_date"):
			conditions.append("os.posting_date <= %(to_date)s")
			values["to_date"] = filters["to_date"]

	if pos_profile:
		conditions.append("os.pos_profile = %(pos_profile)s")
		values["pos_profile"] = pos_profile

	where_clause = "WHERE " + " AND ".join(conditions)

	# ── Rows query (paginated) ────────────────────────────────────────────────
	# Pre-aggregated LEFT JOINs replace 3 correlated subqueries per row.
	rows_query = f"""
		SELECT
			os.name            AS opening_shift_name,
			cs.name            AS closing_shift_name,
			os.posting_date    AS date,
			os.pos_profile,
			os.user            AS cashier,
			os.period_start_date AS open_time,
			cs.period_end_date   AS close_time,
			COALESCE(osd.opening_amount, 0) AS opening_amount,
			COALESCE(csd.closing_amount, 0) AS closing_amount,
			COALESCE(cs.grand_total,     0) AS sales_total,
			COALESCE(csd.difference,     0) AS difference
		FROM `tabPOS Opening Shift` os
		LEFT JOIN `tabPOS Closing Shift` cs
			ON cs.pos_opening_shift = os.name
		LEFT JOIN (
			SELECT parent, SUM(amount) AS opening_amount
			FROM `tabPOS Opening Shift Detail`
			GROUP BY parent
		) osd ON osd.parent = os.name
		LEFT JOIN (
			SELECT
				parent,
				SUM(closing_amount) AS closing_amount,
				SUM(difference)     AS difference
			FROM `tabPOS Closing Shift Detail`
			GROUP BY parent
		) csd ON csd.parent = cs.name
		{where_clause}
		ORDER BY os.posting_date DESC, os.period_start_date DESC
		LIMIT %(limit)s OFFSET %(offset)s
	"""

	data = frappe.db.sql(rows_query, values, as_dict=True)

	for row in data:
		row.opening_amount = flt(row.opening_amount)
		row.closing_amount = flt(row.closing_amount)
		row.sales_total    = flt(row.sales_total)
		row.difference     = flt(row.difference)

	# ── Totals query (no LIMIT) ───────────────────────────────────────────────
	# Runs across the full filter set so summary cards are always accurate
	# regardless of which page the user is viewing.
	totals_query = f"""
		SELECT
			COUNT(*)                              AS total_shifts,
			COALESCE(SUM(cs.grand_total),    0)   AS total_sales,
			COALESCE(SUM(csd_t.difference),  0)   AS total_cash_diff
		FROM `tabPOS Opening Shift` os
		LEFT JOIN `tabPOS Closing Shift` cs
			ON cs.pos_opening_shift = os.name
		LEFT JOIN (
			SELECT parent, SUM(difference) AS difference
			FROM `tabPOS Closing Shift Detail`
			GROUP BY parent
		) csd_t ON csd_t.parent = cs.name
		{where_clause}
	"""
	# Exclude pagination keys from totals query values
	totals_values = {k: v for k, v in values.items() if k not in ("limit", "offset")}
	totals_row = frappe.db.sql(totals_query, totals_values, as_dict=True)
	totals = totals_row[0] if totals_row else {}

	return {
		"rows": data,
		"totals": {
			"total_shifts":    int(totals.get("total_shifts",    len(data))),
			"total_sales":     flt(totals.get("total_sales",     0)),
			"total_cash_diff": flt(totals.get("total_cash_diff", 0)),
		},
	}
