# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""
Sales vs Shifts Report - Calculation Documentation
===================================================

This report analyzes POS shift performance by linking closing shifts to their
associated sales invoices. It calculates metrics to evaluate cashier efficiency,
sales productivity, and shift profitability.

CORE METRICS
------------
- Gross Sales: SUM(grand_total) from non-return invoices
- Returns: SUM(ABS(grand_total)) from return invoices
- Net Sales: Gross Sales - Returns
- Discounts: SUM(discount_amount) from non-return invoices

VOLUME METRICS
--------------
- Invoices: COUNT of non-return invoices
- Items: SUM(total_qty) from non-return invoices
- Customers: COUNT(DISTINCT customer) from non-return invoices

PAYMENT BREAKDOWN
-----------------
- Cash: SUM(amount) where mode_of_payment contains "cash"
- Non-Cash: SUM(amount) for all other payment methods

PERFORMANCE METRICS
-------------------
- Duration: (period_end_date - period_start_date) in hours
- Avg Ticket: Gross Sales / Invoices
- Sales/Hr: Gross Sales / Duration
- Inv/Hr: Invoices / Duration
- Peak Hour: Hour with highest total sales (GROUP BY HOUR, ORDER BY total DESC)

RATE CALCULATIONS
-----------------
- Return Rate: (Returns / Gross Sales) × 100
- Discount Rate: (Discounts / Gross Sales) × 100

EFFICIENCY SCORE (0-100)
------------------------
Base score: 70 points

Factor 1 - Return Rate (-20 to +5):
  - return_rate > 15%: penalty = min(20, (rate - 15) × 2)
  - return_rate ≤ 5%: bonus = +5

Factor 2 - Discount Rate (-10 to +5):
  - discount_rate > 20%: penalty = min(10, (rate - 20))
  - discount_rate ≤ 5%: bonus = +5

Factor 3 - Ticket Size vs Dataset Average (-5 to +10):
  - ratio ≥ 1.5: +10 (50%+ above avg)
  - ratio ≥ 1.2: +5 (20%+ above avg)
  - ratio < 0.7: -5 (30%+ below avg)

Factor 4 - Productivity vs Dataset Average (-5 to +10):
  - ratio ≥ 1.5: +10
  - ratio ≥ 1.2: +5
  - ratio < 0.7: -5

RATING LABELS
-------------
- Efficiency ≥ 90: "Excellent"
- Efficiency ≥ 75: "Good"
- Efficiency ≥ 60: "Average"
- Efficiency < 60: "Needs Improvement"

INVOICE MATCHING
----------------
Invoices are linked to shifts via the `Sales Invoice Reference` child table
(pos_transactions) on `POS Closing Shift`. This is the explicit list of invoices
stored at shift-close time — the authoritative source, no fuzzy matching.
"""

import frappe
from frappe import _
from frappe.utils import flt, cint, time_diff_in_hours, getdate


def execute(filters=None):
	filters = filters or {}
	data = get_shift_data(filters)
	columns = get_columns()
	summary = get_summary(data)
	chart = get_chart(data)
	message = get_report_message(data)
	return columns, data, message, chart, summary


def get_report_message(data):
	"""Generate an informative message with key insights"""
	if not data:
		return None

	# Calculate metrics
	total_shifts = len(data)
	shifts_with_sales = [d for d in data if d.gross_sales > 0]
	shifts_with_sales_count = len(shifts_with_sales)

	# Count ratings (only from shifts with sales - others have no rating)
	excellent_count = len([d for d in data if d.rating == "Excellent"])
	good_count = len([d for d in data if d.rating == "Good"])
	average_count = len([d for d in data if d.rating == "Average"])
	needs_improvement = len([d for d in data if d.rating == "Needs Improvement"])
	no_sales_count = len([d for d in data if d.gross_sales == 0])

	total_gross = sum(d.gross_sales for d in data)
	total_net = sum(d.net_sales for d in data)
	total_returns = sum(d.returns for d in data)
	total_invoices = sum(d.invoices for d in data)

	# Average efficiency only from shifts with sales (0% from no-sales shifts would skew it)
	avg_efficiency = sum(d.efficiency for d in shifts_with_sales) / shifts_with_sales_count if shifts_with_sales_count else 0
	avg_return_rate = (total_returns / total_gross * 100) if total_gross else 0
	avg_ticket = total_gross / total_invoices if total_invoices else 0

	# Efficiency gauge color and status (thresholds match get_rating function)
	if avg_efficiency >= 90:
		gauge_color = "#059669"
		gauge_bg = "#ecfdf5"
		gauge_border = "#a7f3d0"
		status_text = "Excellent"
	elif avg_efficiency >= 75:
		gauge_color = "#2563eb"
		gauge_bg = "#eff6ff"
		gauge_border = "#bfdbfe"
		status_text = "Good"
	elif avg_efficiency >= 60:
		gauge_color = "#d97706"
		gauge_bg = "#fffbeb"
		gauge_border = "#fde68a"
		status_text = "Average"
	else:
		gauge_color = "#dc2626"
		gauge_bg = "#fef2f2"
		gauge_border = "#fecaca"
		status_text = "Needs Work"

	# Build alert if needed
	alerts_html = ""
	if avg_return_rate > 10:
		alerts_html += f'''
			<div class="svs-banner__alert svs-banner__alert--warning">
				<span class="svs-banner__alert-icon">⚠️</span>
				<span class="svs-banner__alert-text" style="color: #991b1b;"><strong>High return rate:</strong> {avg_return_rate:.1f}% — Review return patterns and product issues</span>
			</div>
		'''
	if needs_improvement > total_shifts * 0.3:
		alerts_html += f'''
			<div class="svs-banner__alert svs-banner__alert--info" style="margin-top: {'8px' if avg_return_rate > 10 else ''}">
				<span class="svs-banner__alert-icon">💡</span>
				<span class="svs-banner__alert-text" style="color: #92400e;"><strong>{needs_improvement} shifts</strong> need improvement — Consider additional training</span>
			</div>
		'''

	return f'''
		<style>
			.svs-banner {{
				background: #ffffff;
				border: 1px solid #e5e7eb;
				border-radius: 12px;
				padding: 20px 24px;
				margin-bottom: 16px;
				box-shadow: 0 1px 3px rgba(0,0,0,0.05);
				font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
			}}
			.svs-banner__content {{
				display: flex;
				flex-wrap: wrap;
				gap: 24px;
				align-items: stretch;
			}}
			.svs-banner__gauge {{
				background: {gauge_bg};
				border: 1px solid {gauge_border};
				border-radius: 10px;
				padding: 16px 24px;
				text-align: center;
				min-width: 140px;
			}}
			.svs-banner__gauge-label {{
				font-size: 11px;
				color: #6b7280;
				text-transform: uppercase;
				letter-spacing: 1px;
				margin-bottom: 4px;
			}}
			.svs-banner__gauge-value {{
				font-size: 36px;
				font-weight: 700;
				color: {gauge_color};
				line-height: 1;
			}}
			.svs-banner__gauge-value span {{
				font-size: 18px;
			}}
			.svs-banner__gauge-badge {{
				display: inline-block;
				margin-top: 8px;
				padding: 3px 10px;
				background: {gauge_color};
				color: white;
				border-radius: 12px;
				font-size: 10px;
				font-weight: 600;
				text-transform: uppercase;
			}}
			.svs-banner__metrics {{
				flex: 1;
				min-width: 200px;
			}}
			.svs-banner__metrics-grid {{
				display: grid;
				grid-template-columns: repeat(4, 1fr);
				gap: 12px;
			}}
			.svs-banner__metric {{
				background: #f9fafb;
				border-radius: 8px;
				padding: 12px 8px;
				text-align: center;
			}}
			.svs-banner__metric--alert {{
				background: #fef2f2;
				border: 1px solid #fecaca;
			}}
			.svs-banner__metric-label {{
				font-size: 10px;
				color: #6b7280;
				text-transform: uppercase;
				letter-spacing: 0.5px;
				margin-bottom: 4px;
			}}
			.svs-banner__metric-value {{
				font-size: 20px;
				font-weight: 600;
				color: #111827;
			}}
			.svs-banner__metric-value--danger {{
				color: #dc2626;
			}}
			.svs-banner__distribution {{
				min-width: 180px;
				background: #f9fafb;
				border-radius: 10px;
				padding: 14px 16px;
			}}
			.svs-banner__distribution-title {{
				font-size: 10px;
				color: #6b7280;
				text-transform: uppercase;
				letter-spacing: 0.5px;
				margin-bottom: 12px;
				font-weight: 500;
			}}
			.svs-banner__distribution-bars {{
				display: flex;
				gap: 8px;
				align-items: flex-end;
				height: 44px;
				margin-bottom: 6px;
			}}
			.svs-banner__distribution-bar {{
				flex: 1;
				display: flex;
				flex-direction: column;
				align-items: center;
			}}
			.svs-banner__distribution-labels {{
				display: flex;
				gap: 8px;
				text-align: center;
			}}
			.svs-banner__distribution-item {{
				flex: 1;
			}}
			.svs-banner__distribution-count {{
				font-size: 13px;
				font-weight: 600;
			}}
			.svs-banner__distribution-name {{
				font-size: 8px;
				color: #6b7280;
			}}
			.svs-banner__alert {{
				display: flex;
				align-items: center;
				gap: 8px;
				padding: 10px 14px;
				border-radius: 8px;
				margin-top: 16px;
			}}
			.svs-banner__alert--warning {{
				background: #fef2f2;
				border: 1px solid #fecaca;
			}}
			.svs-banner__alert--info {{
				background: #fffbeb;
				border: 1px solid #fde68a;
			}}
			.svs-banner__alert-icon {{
				font-size: 16px;
			}}
			.svs-banner__alert-text {{
				font-size: 12px;
			}}

			/* Mobile responsive */
			@media screen and (max-width: 768px) {{
				.svs-banner {{
					padding: 14px 16px;
				}}
				.svs-banner__content {{
					gap: 16px;
				}}
				.svs-banner__gauge {{
					width: 100%;
					padding: 14px 16px;
				}}
				.svs-banner__gauge-value {{
					font-size: 32px;
				}}
				.svs-banner__metrics {{
					width: 100%;
					min-width: unset;
				}}
				.svs-banner__metrics-grid {{
					grid-template-columns: repeat(2, 1fr);
					gap: 8px;
				}}
				.svs-banner__metric {{
					padding: 10px 6px;
				}}
				.svs-banner__metric-value {{
					font-size: 18px;
				}}
				.svs-banner__metric-label {{
					font-size: 9px;
				}}
				.svs-banner__distribution {{
					width: 100%;
					min-width: unset;
				}}
			}}

			@media screen and (max-width: 480px) {{
				.svs-banner {{
					padding: 12px;
					border-radius: 10px;
				}}
				.svs-banner__content {{
					gap: 12px;
				}}
				.svs-banner__gauge {{
					padding: 12px;
				}}
				.svs-banner__gauge-value {{
					font-size: 28px;
				}}
				.svs-banner__gauge-value span {{
					font-size: 14px;
				}}
				.svs-banner__gauge-label {{
					font-size: 10px;
				}}
				.svs-banner__metrics-grid {{
					gap: 6px;
				}}
				.svs-banner__metric {{
					padding: 8px 4px;
					border-radius: 6px;
				}}
				.svs-banner__metric-value {{
					font-size: 16px;
				}}
				.svs-banner__metric-label {{
					font-size: 8px;
					letter-spacing: 0.3px;
				}}
				.svs-banner__distribution {{
					padding: 12px;
				}}
				.svs-banner__distribution-bars {{
					height: 36px;
				}}
				.svs-banner__distribution-count {{
					font-size: 12px;
				}}
				.svs-banner__alert {{
					padding: 8px 12px;
					margin-top: 12px;
				}}
				.svs-banner__alert-text {{
					font-size: 11px;
				}}
			}}

			/* Frappe Report Summary - Add spacing below */
			.report-summary {{
				margin-bottom: 20px !important;
			}}

			/* Frappe Report Summary - Mobile Grid Layout */
			@media screen and (max-width: 768px) {{
				.report-summary {{
					display: grid !important;
					grid-template-columns: repeat(2, 1fr) !important;
					gap: 8px !important;
					width: calc(100% - 16px) !important;
					box-sizing: border-box !important;
					padding: 0 !important;
					margin: 0 8px 16px 8px !important;
					overflow: visible !important;
					justify-content: center !important;
				}}
				.report-summary > div,
				.report-summary .summary-item {{
					width: 100% !important;
					min-width: 0 !important;
					max-width: 100% !important;
					box-sizing: border-box !important;
					padding: 12px 6px !important;
					margin: 0 !important;
					text-align: center !important;
					background: #fff;
					border: 1px solid #e9ecef;
					border-radius: 8px;
					overflow: visible !important;
				}}
				.report-summary .summary-label {{
					font-size: 10px !important;
					margin-bottom: 4px !important;
					white-space: normal !important;
					overflow: visible !important;
					word-wrap: break-word !important;
					line-height: 1.3 !important;
					text-decoration: none !important;
				}}
				.report-summary .summary-value {{
					font-size: 15px !important;
					font-weight: 600 !important;
					white-space: nowrap !important;
					overflow: visible !important;
					text-decoration: none !important;
				}}
			}}
			@media screen and (max-width: 400px) {{
				.report-summary {{
					gap: 6px !important;
					width: calc(100% - 12px) !important;
					margin: 0 6px 16px 6px !important;
				}}
				.report-summary > div,
				.report-summary .summary-item {{
					padding: 10px 4px !important;
				}}
				.report-summary .summary-label {{
					font-size: 9px !important;
				}}
				.report-summary .summary-value {{
					font-size: 13px !important;
				}}
			}}
		</style>

		<div class="svs-banner">
			<div class="svs-banner__content">

				<!-- Efficiency Score -->
				<div class="svs-banner__gauge">
					<div class="svs-banner__gauge-label">Efficiency</div>
					<div class="svs-banner__gauge-value">{avg_efficiency:.0f}<span>%</span></div>
					<div class="svs-banner__gauge-badge">{status_text}</div>
				</div>

				<!-- Key Stats -->
				<div class="svs-banner__metrics">
					<div class="svs-banner__metrics-grid">
						<div class="svs-banner__metric">
							<div class="svs-banner__metric-label">Shifts</div>
							<div class="svs-banner__metric-value">{total_shifts}</div>
						</div>
						<div class="svs-banner__metric">
							<div class="svs-banner__metric-label">Invoices</div>
							<div class="svs-banner__metric-value">{total_invoices:,}</div>
						</div>
						<div class="svs-banner__metric">
							<div class="svs-banner__metric-label">Avg Ticket</div>
							<div class="svs-banner__metric-value">{avg_ticket:,.0f}</div>
						</div>
						<div class="svs-banner__metric {'svs-banner__metric--alert' if avg_return_rate > 10 else ''}">
							<div class="svs-banner__metric-label">Return Rate</div>
							<div class="svs-banner__metric-value {'svs-banner__metric-value--danger' if avg_return_rate > 10 else ''}">{avg_return_rate:.1f}%</div>
						</div>
					</div>
				</div>

				<!-- Rating Distribution -->
				<div class="svs-banner__distribution">
					<div class="svs-banner__distribution-title">Performance Distribution</div>
					<div class="svs-banner__distribution-bars">
						<div class="svs-banner__distribution-bar">
							<div style="width: 100%; background: #10b981; border-radius: 4px 4px 0 0; height: {max(6, excellent_count / max(excellent_count, good_count, average_count, needs_improvement, 1) * 44)}px;"></div>
						</div>
						<div class="svs-banner__distribution-bar">
							<div style="width: 100%; background: #3b82f6; border-radius: 4px 4px 0 0; height: {max(6, good_count / max(excellent_count, good_count, average_count, needs_improvement, 1) * 44)}px;"></div>
						</div>
						<div class="svs-banner__distribution-bar">
							<div style="width: 100%; background: #f59e0b; border-radius: 4px 4px 0 0; height: {max(6, average_count / max(excellent_count, good_count, average_count, needs_improvement, 1) * 44)}px;"></div>
						</div>
						<div class="svs-banner__distribution-bar">
							<div style="width: 100%; background: #ef4444; border-radius: 4px 4px 0 0; height: {max(6, needs_improvement / max(excellent_count, good_count, average_count, needs_improvement, 1) * 44)}px;"></div>
						</div>
					</div>
					<div class="svs-banner__distribution-labels">
						<div class="svs-banner__distribution-item">
							<div class="svs-banner__distribution-count" style="color: #10b981;">{excellent_count}</div>
							<div class="svs-banner__distribution-name">Excellent</div>
						</div>
						<div class="svs-banner__distribution-item">
							<div class="svs-banner__distribution-count" style="color: #3b82f6;">{good_count}</div>
							<div class="svs-banner__distribution-name">Good</div>
						</div>
						<div class="svs-banner__distribution-item">
							<div class="svs-banner__distribution-count" style="color: #f59e0b;">{average_count}</div>
							<div class="svs-banner__distribution-name">Average</div>
						</div>
						<div class="svs-banner__distribution-item">
							<div class="svs-banner__distribution-count" style="color: #ef4444;">{needs_improvement}</div>
							<div class="svs-banner__distribution-name">Low</div>
						</div>
					</div>
				</div>

			</div>

			{alerts_html}
		</div>
	'''


# =============================================================================
# COLUMNS
# =============================================================================

def get_columns():
	return [
		# Shift Identity
		{"fieldname": "shift_id", "label": _("Shift ID"), "fieldtype": "Link", "options": "POS Closing Shift", "width": 120},
		{"fieldname": "shift_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "shift_start", "label": _("Start"), "fieldtype": "Data", "width": 70},
		{"fieldname": "shift_end", "label": _("End"), "fieldtype": "Data", "width": 70},
		{"fieldname": "duration_hrs", "label": _("Hours"), "fieldtype": "Float", "precision": 1, "width": 70},

		# People
		{"fieldname": "pos_profile", "label": _("POS Profile"), "fieldtype": "Link", "options": "POS Profile", "width": 120},
		{"fieldname": "cashier", "label": _("Cashier"), "fieldtype": "Data", "width": 120},
		{"fieldname": "sales_person", "label": _("Sales Person"), "fieldtype": "Data", "width": 120},

		# Sales Metrics
		{"fieldname": "gross_sales", "label": _("Gross Sales"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "returns", "label": _("Returns"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "net_sales", "label": _("Net Sales"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "discounts", "label": _("Discounts"), "fieldtype": "Currency", "width": 100},

		# Volume Metrics
		{"fieldname": "invoices", "label": _("Invoices"), "fieldtype": "Int", "width": 80},
		{"fieldname": "qty_sold", "label": _("Items"), "fieldtype": "Int", "width": 70},
		{"fieldname": "customers", "label": _("Customers"), "fieldtype": "Int", "width": 90},

		# Payment Breakdown
		{"fieldname": "cash", "label": _("Cash"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "non_cash", "label": _("Non-Cash"), "fieldtype": "Currency", "width": 100},

		# Performance Metrics
		{"fieldname": "avg_ticket", "label": _("Avg Ticket"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "sales_per_hour", "label": _("Sales/Hr"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "invoices_per_hour", "label": _("Inv/Hr"), "fieldtype": "Float", "precision": 1, "width": 70},

		# Analysis
		{"fieldname": "peak_hour", "label": _("Peak Hour"), "fieldtype": "Data", "width": 90},
		{"fieldname": "return_rate", "label": _("Return %"), "fieldtype": "Percent", "width": 80},
		{"fieldname": "discount_rate", "label": _("Disc %"), "fieldtype": "Percent", "width": 80},
		{"fieldname": "efficiency", "label": _("Efficiency"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "rating", "label": _("Rating"), "fieldtype": "Data", "width": 110},
	]


# =============================================================================
# DATA FETCHING
# =============================================================================

def get_shift_data(filters):
	"""Fetch and process shift data with all metrics"""

	# Get base shift data with aggregated invoice metrics
	shifts = fetch_shifts_with_invoices(filters)

	if not shifts:
		return []

	# Fetch payment data in batch
	payment_data = fetch_payment_data_batch(shifts)

	# Fetch sales person data in batch
	salesperson_data = fetch_salesperson_data_batch(shifts)

	# Fetch peak hours in batch
	peak_hour_data = fetch_peak_hours_batch(shifts)

	# Fetch cashier names in batch
	cashier_ids = list(set(s.cashier_id for s in shifts if s.cashier_id))
	cashier_names = {}
	if cashier_ids:
		cashier_names = {
			u.name: u.full_name or u.name
			for u in frappe.get_all("User", filters={"name": ["in", cashier_ids]}, fields=["name", "full_name"])
		}

	# Calculate dataset statistics for relative efficiency scoring
	stats = calculate_statistics(shifts)

	# Enrich each shift with computed fields
	for shift in shifts:
		enrich_shift_data(shift, payment_data, salesperson_data, peak_hour_data, cashier_names, stats)

	# Apply sales person filter (post-processing)
	if filters.get("sales_person"):
		sp_filter = filters.get("sales_person")
		shifts = [s for s in shifts if sp_filter in (s.sales_person or "")]

	return shifts


def fetch_shifts_with_invoices(filters):
	"""Fetch shifts with aggregated invoice data in a single query.

	Uses the `Sales Invoice Reference` child table (pos_transactions) on POS Closing Shift
	as the authoritative link between shifts and invoices. This is the explicit list stored
	at shift-close time — no fuzzy matching by date/user/profile.
	"""

	conditions = build_conditions(filters)

	query = """
		SELECT
			pcs.name AS shift_id,
			pcs.pos_profile,
			pcs.user AS cashier_id,
			pcs.period_start_date,
			pcs.period_end_date,
			pcs.pos_opening_shift,

			COALESCE(SUM(CASE WHEN si.is_return = 0 THEN si.grand_total ELSE 0 END), 0) AS gross_sales,
			COALESCE(SUM(CASE WHEN si.is_return = 1 THEN ABS(si.grand_total) ELSE 0 END), 0) AS returns,
			COALESCE(SUM(CASE WHEN si.is_return = 0 THEN si.discount_amount ELSE 0 END), 0) AS discounts,
			COALESCE(SUM(CASE WHEN si.is_return = 0 THEN si.total_qty ELSE 0 END), 0) AS qty_sold,

			COUNT(CASE WHEN si.is_return = 0 THEN 1 END) AS invoices,
			COUNT(CASE WHEN si.is_return = 1 THEN 1 END) AS return_count,
			COUNT(DISTINCT CASE WHEN si.is_return = 0 THEN si.customer END) AS customers

		FROM `tabPOS Closing Shift` pcs
		LEFT JOIN `tabSales Invoice Reference` sir ON sir.parent = pcs.name
			AND sir.parenttype = 'POS Closing Shift'
		LEFT JOIN `tabSales Invoice` si ON si.name = sir.sales_invoice
			AND si.docstatus = 1
		WHERE pcs.docstatus = 1
		{conditions}
		GROUP BY pcs.name
		ORDER BY pcs.period_start_date DESC
	""".format(conditions=conditions)

	return frappe.db.sql(query, filters, as_dict=True)


def build_conditions(filters):
	"""Build SQL WHERE conditions"""
	conditions = []

	if filters.get("from_date"):
		conditions.append("DATE(pcs.period_start_date) >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("DATE(pcs.period_end_date) <= %(to_date)s")
	if filters.get("pos_profile"):
		conditions.append("pcs.pos_profile = %(pos_profile)s")
	if filters.get("cashier"):
		conditions.append("pcs.user = %(cashier)s")
	if filters.get("shift"):
		conditions.append("pcs.name = %(shift)s")

	return "AND " + " AND ".join(conditions) if conditions else ""


# =============================================================================
# BATCH DATA FETCHING
# =============================================================================

def fetch_payment_data_batch(shifts):
	"""Fetch payment breakdown for all shifts"""
	if not shifts:
		return {}

	result = {}
	for shift in shifts:
		result[shift.shift_id] = fetch_payment_data_single(shift)

	return result


def fetch_payment_data_single(shift):
	"""Fetch payment data for a single shift via pos_transactions child table"""
	query = """
		SELECT
			LOWER(sip.mode_of_payment) AS mode,
			SUM(sip.amount) AS amount
		FROM `tabSales Invoice Payment` sip
		INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
		INNER JOIN `tabSales Invoice Reference` sir ON sir.sales_invoice = si.name
			AND sir.parent = %(shift)s
			AND sir.parenttype = 'POS Closing Shift'
		WHERE si.docstatus = 1 AND si.is_return = 0
		GROUP BY LOWER(sip.mode_of_payment)
	"""

	payments = frappe.db.sql(query, {
		"shift": shift.shift_id,
	}, as_dict=True)

	cash = 0
	non_cash = 0
	for p in payments:
		if "cash" in (p.mode or ""):
			cash += flt(p.amount)
		else:
			non_cash += flt(p.amount)

	return {"cash": cash, "non_cash": non_cash}


def fetch_salesperson_data_batch(shifts):
	"""Fetch sales person data for all shifts"""
	result = {}
	for shift in shifts:
		result[shift.shift_id] = fetch_salesperson_data_single(shift)
	return result


def fetch_salesperson_data_single(shift):
	"""Fetch sales person data for a single shift via pos_transactions child table"""
	query = """
		SELECT
			st.sales_person,
			SUM(st.allocated_amount) AS contribution
		FROM `tabSales Team` st
		INNER JOIN `tabSales Invoice` si ON si.name = st.parent
		INNER JOIN `tabSales Invoice Reference` sir ON sir.sales_invoice = si.name
			AND sir.parent = %(shift)s
			AND sir.parenttype = 'POS Closing Shift'
		WHERE si.docstatus = 1 AND si.is_return = 0
		GROUP BY st.sales_person
		ORDER BY contribution DESC
	"""

	sales_persons = frappe.db.sql(query, {
		"shift": shift.shift_id,
	}, as_dict=True)

	if not sales_persons:
		return {"names": "", "contribution": 0}

	# Get names
	names = []
	total = 0
	for sp in sales_persons[:3]:  # Top 3
		sp_name = frappe.db.get_value("Sales Person", sp.sales_person, "sales_person_name") or sp.sales_person
		names.append(sp_name)
		total += flt(sp.contribution)

	# Add remaining contribution
	for sp in sales_persons[3:]:
		total += flt(sp.contribution)

	name_str = ", ".join(names)
	if len(sales_persons) > 3:
		name_str += f" +{len(sales_persons) - 3}"

	return {"names": name_str, "contribution": total}


def fetch_peak_hours_batch(shifts):
	"""Fetch peak hour for all shifts"""
	result = {}
	for shift in shifts:
		result[shift.shift_id] = fetch_peak_hour_single(shift)
	return result


def fetch_peak_hour_single(shift):
	"""Fetch peak hour for a single shift via pos_transactions child table"""
	query = """
		SELECT HOUR(si.posting_time) AS hour, SUM(si.grand_total) AS total
		FROM `tabSales Invoice` si
		INNER JOIN `tabSales Invoice Reference` sir ON sir.sales_invoice = si.name
			AND sir.parent = %(shift)s
			AND sir.parenttype = 'POS Closing Shift'
		WHERE si.docstatus = 1 AND si.is_return = 0
		GROUP BY HOUR(si.posting_time)
		ORDER BY total DESC
		LIMIT 1
	"""

	result = frappe.db.sql(query, {
		"shift": shift.shift_id,
	}, as_dict=True)

	if result and result[0].hour is not None:
		h = cint(result[0].hour)
		return f"{h:02d}:00"
	return ""


# =============================================================================
# DATA ENRICHMENT
# =============================================================================

def enrich_shift_data(shift, payment_data, salesperson_data, peak_hour_data, cashier_names, stats):
	"""Add computed fields to shift data"""

	# Time fields
	if shift.period_start_date:
		shift.shift_date = getdate(shift.period_start_date)
		shift.shift_start = shift.period_start_date.strftime("%H:%M") if hasattr(shift.period_start_date, 'strftime') else ""
	else:
		shift.shift_date = None
		shift.shift_start = ""

	if shift.period_end_date:
		shift.shift_end = shift.period_end_date.strftime("%H:%M") if hasattr(shift.period_end_date, 'strftime') else ""
	else:
		shift.shift_end = ""

	# Duration
	if shift.period_start_date and shift.period_end_date:
		shift.duration_hrs = flt(time_diff_in_hours(shift.period_end_date, shift.period_start_date), 1)
	else:
		shift.duration_hrs = 0

	# Cashier name
	shift.cashier = cashier_names.get(shift.cashier_id) or shift.cashier_id or ""

	# Net sales
	shift.net_sales = flt(shift.gross_sales - shift.returns, 2)

	# Payment breakdown
	payments = payment_data.get(shift.shift_id, {})
	shift.cash = flt(payments.get("cash", 0), 2)
	shift.non_cash = flt(payments.get("non_cash", 0), 2)

	# Sales person
	sp_data = salesperson_data.get(shift.shift_id, {})
	shift.sales_person = sp_data.get("names", "")

	# Peak hour
	shift.peak_hour = peak_hour_data.get(shift.shift_id, "")

	# Performance metrics
	if shift.invoices > 0:
		shift.avg_ticket = flt(shift.gross_sales / shift.invoices, 2)
	else:
		shift.avg_ticket = 0

	if shift.duration_hrs > 0:
		shift.sales_per_hour = flt(shift.gross_sales / shift.duration_hrs, 2)
		shift.invoices_per_hour = flt(shift.invoices / shift.duration_hrs, 1)
	else:
		shift.sales_per_hour = 0
		shift.invoices_per_hour = 0

	# Rates
	if shift.gross_sales > 0:
		shift.return_rate = flt((shift.returns / shift.gross_sales) * 100, 1)
		shift.discount_rate = flt((shift.discounts / shift.gross_sales) * 100, 1)
	else:
		shift.return_rate = 0
		shift.discount_rate = 0

	# Efficiency and rating
	shift.efficiency = calculate_efficiency(shift, stats)
	shift.rating = get_rating(shift.efficiency, shift.gross_sales)


# =============================================================================
# EFFICIENCY CALCULATION
# =============================================================================

def calculate_statistics(shifts):
	"""Calculate dataset statistics for relative comparisons"""
	active_shifts = [s for s in shifts if s.gross_sales > 0]

	if not active_shifts:
		return {"avg_ticket": 0, "avg_invoices_per_hour": 0}

	# Calculate averages
	total_sales = sum(s.gross_sales for s in active_shifts)
	total_invoices = sum(s.invoices for s in active_shifts)

	avg_ticket = total_sales / total_invoices if total_invoices > 0 else 0

	# Average invoices per hour (only for shifts with duration)
	shifts_with_duration = [s for s in active_shifts if s.period_start_date and s.period_end_date]
	if shifts_with_duration:
		total_hours = sum(time_diff_in_hours(s.period_end_date, s.period_start_date) for s in shifts_with_duration)
		total_inv = sum(s.invoices for s in shifts_with_duration)
		avg_inv_per_hour = total_inv / total_hours if total_hours > 0 else 0
	else:
		avg_inv_per_hour = 0

	return {
		"avg_ticket": avg_ticket,
		"avg_invoices_per_hour": avg_inv_per_hour
	}


def calculate_efficiency(shift, stats):
	"""Calculate efficiency score (0-100) using relative comparisons"""

	# No sales = no efficiency to measure
	if shift.gross_sales == 0 or shift.invoices == 0:
		return 0

	score = 70  # Base score

	# Factor 1: Return rate penalty/bonus (-20 to +5)
	if shift.return_rate > 15:
		score -= min(20, (shift.return_rate - 15) * 2)
	elif shift.return_rate <= 5:
		score += 5

	# Factor 2: Discount rate penalty/bonus (-10 to +5)
	if shift.discount_rate > 20:
		score -= min(10, (shift.discount_rate - 20))
	elif shift.discount_rate <= 5:
		score += 5

	# Factor 3: Ticket size vs average (-5 to +10)
	avg_ticket = stats.get("avg_ticket", 0)
	if avg_ticket > 0 and shift.avg_ticket > 0:
		ratio = shift.avg_ticket / avg_ticket
		if ratio >= 1.5:
			score += 10
		elif ratio >= 1.2:
			score += 5
		elif ratio < 0.7:
			score -= 5

	# Factor 4: Productivity vs average (-5 to +10)
	avg_inv_hr = stats.get("avg_invoices_per_hour", 0)
	if avg_inv_hr > 0 and shift.invoices_per_hour > 0:
		ratio = shift.invoices_per_hour / avg_inv_hr
		if ratio >= 1.5:
			score += 10
		elif ratio >= 1.2:
			score += 5
		elif ratio < 0.7:
			score -= 5

	return max(0, min(100, flt(score, 1)))


def get_rating(efficiency, gross_sales):
	"""Get rating label based on efficiency"""
	if gross_sales == 0:
		return ""
	if efficiency >= 90:
		return "Excellent"
	if efficiency >= 75:
		return "Good"
	if efficiency >= 60:
		return "Average"
	return "Needs Improvement"


# =============================================================================
# SUMMARY
# =============================================================================

def get_summary(data):
	"""Generate report summary cards"""
	if not data:
		return None

	total_shifts = len(data)
	total_gross = sum(d.gross_sales for d in data)
	total_net = sum(d.net_sales for d in data)
	total_invoices = sum(d.invoices for d in data)
	total_items = sum(d.qty_sold for d in data)
	total_customers = sum(d.customers for d in data)
	total_returns = sum(d.returns for d in data)
	total_discounts = sum(d.discounts for d in data)
	total_cash = sum(d.cash for d in data)
	total_non_cash = sum(d.non_cash for d in data)

	# Average efficiency only from shifts with sales (0% from no-sales shifts would skew it)
	shifts_with_sales = [d for d in data if d.gross_sales > 0]
	shifts_with_sales_count = len(shifts_with_sales)
	avg_efficiency = sum(d.efficiency for d in shifts_with_sales) / shifts_with_sales_count if shifts_with_sales_count else 0
	avg_ticket = total_gross / total_invoices if total_invoices else 0

	excellent = len([d for d in data if d.rating == "Excellent"])
	good = len([d for d in data if d.rating == "Good"])

	return [
		{"value": total_shifts, "label": _("Shifts"), "datatype": "Int", "indicator": "Blue"},
		{"value": total_gross, "label": _("Gross Sales"), "datatype": "Currency", "indicator": "Green"},
		{"value": total_net, "label": _("Net Sales"), "datatype": "Currency", "indicator": "Green"},
		{"value": total_invoices, "label": _("Invoices"), "datatype": "Int", "indicator": "Blue"},
		{"value": total_items, "label": _("Items Sold"), "datatype": "Int", "indicator": "Blue"},
		{"value": total_customers, "label": _("Customers"), "datatype": "Int", "indicator": "Blue"},
		{"value": avg_ticket, "label": _("Avg Ticket"), "datatype": "Currency", "indicator": "Purple"},
		{"value": total_cash, "label": _("Cash"), "datatype": "Currency", "indicator": "Orange"},
		{"value": total_non_cash, "label": _("Non-Cash"), "datatype": "Currency", "indicator": "Purple"},
		{"value": total_returns, "label": _("Returns"), "datatype": "Currency", "indicator": "Red"},
		{"value": total_discounts, "label": _("Discounts"), "datatype": "Currency", "indicator": "Orange"},
		{"value": avg_efficiency, "label": _("Avg Efficiency"), "datatype": "Percent",
		 "indicator": "Green" if avg_efficiency >= 90 else "Blue" if avg_efficiency >= 75 else "Orange" if avg_efficiency >= 60 else "Red"},
		{"value": excellent + good, "label": _("High Performers"), "datatype": "Int", "indicator": "Green"},
	]


# =============================================================================
# CHART
# =============================================================================

def get_chart(data):
	"""Generate default chart - Sales performance by shift with efficiency overlay"""
	if not data:
		return None

	# Get recent shifts, sorted by date
	recent = sorted(data[:20], key=lambda x: x.shift_date or "", reverse=False)[-15:]

	if not recent:
		return None

	# Build labels: Short date format
	labels = []
	for d in recent:
		if hasattr(d.shift_date, 'strftime'):
			labels.append(d.shift_date.strftime("%d %b"))
		else:
			labels.append(d.shift_id[:8] if d.shift_id else "-")

	# Ensure all values are valid numbers
	net_sales_values = [flt(d.net_sales or 0) for d in recent]
	gross_sales_values = [flt(d.gross_sales or 0) for d in recent]
	returns_values = [flt(d.returns or 0) for d in recent]

	# Don't render chart if no sales data
	if not any(net_sales_values) and not any(gross_sales_values):
		return None

	# Simple, clean bar chart showing sales breakdown
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{
					"name": _("Net Sales"),
					"values": net_sales_values
				},
				{
					"name": _("Returns"),
					"values": returns_values
				}
			]
		},
		"type": "bar",
		"colors": ["#10b981", "#ef4444"],
		"height": 280,
		"barOptions": {
			"spaceRatio": 0.4,
			"stacked": False
		}
	}


# =============================================================================
# API ENDPOINTS FOR CHARTS
# =============================================================================

@frappe.whitelist()
def get_hourly_breakdown(filters):
	"""Get hourly sales breakdown"""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters

	conditions = []
	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")
	if filters.get("pos_profile"):
		conditions.append("si.pos_profile = %(pos_profile)s")
	if filters.get("cashier"):
		conditions.append("si.owner = %(cashier)s")

	where = " AND " + " AND ".join(conditions) if conditions else ""

	return frappe.db.sql("""
		SELECT
			HOUR(si.posting_time) AS hour,
			COUNT(*) AS invoice_count,
			SUM(si.grand_total) AS total_sales
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1 AND si.is_pos = 1 AND si.is_return = 0
		{where}
		GROUP BY HOUR(si.posting_time)
		ORDER BY hour
	""".format(where=where), filters, as_dict=True)


@frappe.whitelist()
def get_payment_method_breakdown(filters):
	"""Get payment method breakdown"""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters

	conditions = []
	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")
	if filters.get("pos_profile"):
		conditions.append("si.pos_profile = %(pos_profile)s")
	if filters.get("cashier"):
		conditions.append("si.owner = %(cashier)s")

	where = " AND " + " AND ".join(conditions) if conditions else ""

	return frappe.db.sql("""
		SELECT
			sip.mode_of_payment,
			COUNT(DISTINCT si.name) AS transaction_count,
			SUM(sip.amount) AS total_amount
		FROM `tabSales Invoice Payment` sip
		INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
		WHERE si.docstatus = 1 AND si.is_pos = 1 AND si.is_return = 0
		{where}
		GROUP BY sip.mode_of_payment
		ORDER BY total_amount DESC
	""".format(where=where), filters, as_dict=True)


@frappe.whitelist()
def get_daily_trend(filters):
	"""Get daily sales trend"""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters

	conditions = []
	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")
	if filters.get("pos_profile"):
		conditions.append("si.pos_profile = %(pos_profile)s")
	if filters.get("cashier"):
		conditions.append("si.owner = %(cashier)s")

	where = " AND " + " AND ".join(conditions) if conditions else ""

	return frappe.db.sql("""
		SELECT
			si.posting_date AS date,
			COUNT(*) AS invoice_count,
			SUM(si.grand_total) AS total_sales
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1 AND si.is_pos = 1 AND si.is_return = 0
		{where}
		GROUP BY si.posting_date
		ORDER BY si.posting_date
	""".format(where=where), filters, as_dict=True)
