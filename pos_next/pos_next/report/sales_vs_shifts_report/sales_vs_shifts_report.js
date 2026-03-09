// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

frappe.query_reports["Sales vs Shifts Report"] = {
	// =========================================================================
	// REPORT CALCULATION GUIDE
	// =========================================================================
	// This report analyzes POS shift performance by linking closing shifts to
	// their associated sales invoices. It calculates metrics to evaluate
	// cashier efficiency, sales productivity, and shift profitability.
	//
	// -------------------------------------------------------------------------
	// CORE METRICS
	// -------------------------------------------------------------------------
	//
	// GROSS SALES
	//   Formula: SUM of grand_total from all non-return invoices in the shift
	//   Source: Sales Invoice.grand_total WHERE is_return = 0
	//
	// RETURNS
	//   Formula: SUM of ABS(grand_total) from all return invoices in the shift
	//   Source: ABS(Sales Invoice.grand_total) WHERE is_return = 1
	//
	// NET SALES
	//   Formula: Gross Sales - Returns
	//   Example: If Gross = 10,000 and Returns = 500, then Net = 9,500
	//
	// DISCOUNTS
	//   Formula: SUM of discount_amount from all non-return invoices
	//   Source: Sales Invoice.discount_amount WHERE is_return = 0
	//
	// -------------------------------------------------------------------------
	// VOLUME METRICS
	// -------------------------------------------------------------------------
	//
	// INVOICES
	//   Formula: COUNT of non-return invoices
	//   Source: COUNT(Sales Invoice) WHERE is_return = 0
	//
	// ITEMS (Qty Sold)
	//   Formula: SUM of total_qty from all non-return invoices
	//   Source: Sales Invoice.total_qty WHERE is_return = 0
	//
	// CUSTOMERS
	//   Formula: COUNT DISTINCT customers from non-return invoices
	//   Source: COUNT(DISTINCT Sales Invoice.customer) WHERE is_return = 0
	//
	// -------------------------------------------------------------------------
	// PAYMENT BREAKDOWN
	// -------------------------------------------------------------------------
	//
	// CASH
	//   Formula: SUM of payments where mode_of_payment contains "cash"
	//   Source: Sales Invoice Payment.amount WHERE mode LIKE '%cash%'
	//
	// NON-CASH
	//   Formula: SUM of all other payment methods (card, mobile, etc.)
	//   Source: Sales Invoice Payment.amount WHERE mode NOT LIKE '%cash%'
	//
	// -------------------------------------------------------------------------
	// PERFORMANCE METRICS
	// -------------------------------------------------------------------------
	//
	// DURATION (Hours)
	//   Formula: (period_end_date - period_start_date) in hours
	//   Example: Start 09:00, End 17:00 = 8 hours
	//
	// AVG TICKET
	//   Formula: Gross Sales / Number of Invoices
	//   Example: 10,000 / 50 invoices = 200 average per transaction
	//
	// SALES/HR (Sales per Hour)
	//   Formula: Gross Sales / Duration Hours
	//   Example: 10,000 / 8 hours = 1,250 per hour
	//
	// INV/HR (Invoices per Hour)
	//   Formula: Number of Invoices / Duration Hours
	//   Example: 50 invoices / 8 hours = 6.25 invoices per hour
	//
	// PEAK HOUR
	//   Formula: Hour with highest total sales during the shift
	//   Method: GROUP BY HOUR(posting_time), ORDER BY total DESC, LIMIT 1
	//   Example: "14:00" means 2pm had the most sales
	//
	// -------------------------------------------------------------------------
	// RATE CALCULATIONS
	// -------------------------------------------------------------------------
	//
	// RETURN RATE (Return %)
	//   Formula: (Returns / Gross Sales) × 100
	//   Example: 500 returns / 10,000 gross = 5%
	//   Warning: Highlighted red if > 10%
	//
	// DISCOUNT RATE (Disc %)
	//   Formula: (Discounts / Gross Sales) × 100
	//   Example: 800 discounts / 10,000 gross = 8%
	//
	// -------------------------------------------------------------------------
	// EFFICIENCY SCORE (0-100)
	// -------------------------------------------------------------------------
	//
	// Base Score: 70 points
	//
	// Factor 1: RETURN RATE ADJUSTMENT (-20 to +5 points)
	//   - If return_rate > 15%: Penalty = min(20, (rate - 15) × 2)
	//   - If return_rate ≤ 5%: Bonus = +5 points
	//   Example: 18% return rate → penalty = min(20, 6) = -6 points
	//
	// Factor 2: DISCOUNT RATE ADJUSTMENT (-10 to +5 points)
	//   - If discount_rate > 20%: Penalty = min(10, (rate - 20))
	//   - If discount_rate ≤ 5%: Bonus = +5 points
	//   Example: 25% discount rate → penalty = min(10, 5) = -5 points
	//
	// Factor 3: TICKET SIZE vs AVERAGE (-5 to +10 points)
	//   Dataset Average Ticket = Total Sales / Total Invoices (all shifts)
	//   Ratio = Shift Avg Ticket / Dataset Avg Ticket
	//   - If ratio ≥ 1.5: Bonus = +10 points (50%+ above average)
	//   - If ratio ≥ 1.2: Bonus = +5 points (20%+ above average)
	//   - If ratio < 0.7: Penalty = -5 points (30%+ below average)
	//
	// Factor 4: PRODUCTIVITY vs AVERAGE (-5 to +10 points)
	//   Dataset Avg Inv/Hr = Total Invoices / Total Hours (all shifts)
	//   Ratio = Shift Inv/Hr / Dataset Avg Inv/Hr
	//   - If ratio ≥ 1.5: Bonus = +10 points
	//   - If ratio ≥ 1.2: Bonus = +5 points
	//   - If ratio < 0.7: Penalty = -5 points
	//
	// EFFICIENCY RANGE: Capped between 0 and 100
	//
	// Example Calculation:
	//   Base:          70
	//   Return 3%:     +5 (≤5%, bonus)
	//   Discount 8%:    0 (between 5-20%, no change)
	//   Ticket 1.3×:   +5 (≥1.2× average)
	//   Inv/Hr 0.6×:   -5 (<0.7× average)
	//   ─────────────────
	//   Final:         75
	//
	// -------------------------------------------------------------------------
	// RATING LABELS
	// -------------------------------------------------------------------------
	//
	//   Efficiency ≥ 90  →  "Excellent"  (Green)
	//   Efficiency ≥ 75  →  "Good"       (Blue)
	//   Efficiency ≥ 60  →  "Average"    (Yellow)
	//   Efficiency < 60  →  "Needs Improvement" (Red)
	//   No sales (0)     →  (blank)
	//
	// -------------------------------------------------------------------------
	// INVOICE MATCHING LOGIC
	// -------------------------------------------------------------------------
	//
	// Invoices are linked to shifts via the Sales Invoice Reference child table
	// (pos_transactions) on POS Closing Shift. This is the explicit list stored
	// at shift-close time — the authoritative source, no fuzzy matching.
	//
	// =========================================================================

	onload: function(report) {
		// Add "Guide" button with icon
		report.page.add_inner_button(__("Report Guide"), function() {
			this.show_report_guide();
		}.bind(this));
	},

	show_report_guide: function() {
		const dialog = new frappe.ui.Dialog({
			title: __("Sales vs Shifts Report Guide"),
			size: "extra-large",
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "guide_content"
				}
			]
		});

		dialog.fields_dict.guide_content.$wrapper.html(this.get_guide_html());
		dialog.show();

		// Add tab functionality after dialog is shown
		setTimeout(() => {
			const tabs = dialog.$wrapper.find(".guide-tab");
			const contents = dialog.$wrapper.find(".guide-tab-content");

			tabs.on("click", function() {
				const target = $(this).data("tab");
				tabs.removeClass("active");
				$(this).addClass("active");
				contents.removeClass("active");
				dialog.$wrapper.find(`[data-content="${target}"]`).addClass("active");
			});
		}, 100);
	},

	get_guide_html: function() {
		return `
			<style>
				.guide-container { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
				.guide-header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 24px; border-radius: 12px; margin-bottom: 20px; }
				.guide-header h2 { margin: 0 0 8px 0; font-size: 22px; font-weight: 600; }
				.guide-header p { margin: 0; opacity: 0.85; font-size: 14px; }
				.guide-tabs { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
				.guide-tab { padding: 10px 20px; background: #f1f3f5; border: none; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 500; color: #495057; transition: all 0.2s; }
				.guide-tab:hover { background: #e9ecef; }
				.guide-tab.active { background: #4263eb; color: white; }
				.guide-tab-content { display: none; }
				.guide-tab-content.active { display: block; }
				.metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
				.metric-card { background: #fff; border: 1px solid #e9ecef; border-radius: 10px; padding: 16px; transition: box-shadow 0.2s; }
				.metric-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
				.metric-card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
				.metric-icon { width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 16px; }
				.metric-card-title { font-weight: 600; font-size: 14px; color: #212529; }
				.metric-card-subtitle { font-size: 11px; color: #868e96; }
				.metric-list { margin: 0; padding: 0; list-style: none; }
				.metric-list li { padding: 8px 0; border-bottom: 1px solid #f1f3f5; font-size: 13px; display: flex; justify-content: space-between; }
				.metric-list li:last-child { border-bottom: none; }
				.metric-name { color: #495057; }
				.metric-formula { color: #868e96; font-size: 11px; font-family: monospace; background: #f8f9fa; padding: 2px 6px; border-radius: 4px; }
				.efficiency-breakdown { background: linear-gradient(135deg, #f8f9fa 0%, #fff 100%); border-radius: 12px; padding: 20px; }
				.efficiency-base { text-align: center; padding: 20px; background: #4263eb; color: white; border-radius: 10px; margin-bottom: 16px; }
				.efficiency-base-number { font-size: 48px; font-weight: 700; }
				.efficiency-base-label { font-size: 13px; opacity: 0.9; }
				.factor-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
				.factor-card { background: white; border-radius: 8px; padding: 14px; border: 1px solid #e9ecef; }
				.factor-title { font-weight: 600; font-size: 12px; color: #495057; margin-bottom: 8px; }
				.factor-row { display: flex; justify-content: space-between; font-size: 12px; padding: 4px 0; }
				.factor-condition { color: #666; }
				.factor-points { font-weight: 600; }
				.factor-points.positive { color: #2f9e44; }
				.factor-points.negative { color: #e03131; }
				.rating-scale { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 16px; }
				.rating-badge { padding: 12px 20px; border-radius: 10px; color: white; font-weight: 600; font-size: 13px; text-align: center; min-width: 140px; }
				.rating-badge span { display: block; font-size: 11px; font-weight: 400; opacity: 0.9; margin-top: 4px; }
				.chart-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
				.chart-card { background: #f8f9fa; border-radius: 10px; padding: 16px; border-left: 4px solid #4263eb; }
				.chart-card-title { font-weight: 600; font-size: 13px; color: #212529; margin-bottom: 6px; }
				.chart-card-desc { font-size: 12px; color: #666; line-height: 1.5; }
				.tip-list { margin: 0; padding: 0; list-style: none; }
				.tip-item { display: flex; gap: 12px; padding: 14px; background: #fff; border-radius: 10px; margin-bottom: 10px; border: 1px solid #e9ecef; }
				.tip-icon { width: 32px; height: 32px; background: #fff3bf; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
				.tip-content { flex: 1; }
				.tip-title { font-weight: 600; font-size: 13px; color: #212529; margin-bottom: 4px; }
				.tip-desc { font-size: 12px; color: #666; line-height: 1.5; }
			</style>

			<div class="guide-container">
				<div class="guide-header">
					<h2>Understanding Your Shift Performance</h2>
					<p>Analyze cashier productivity, identify top performers, and optimize your POS operations</p>
				</div>

				<div class="guide-tabs">
					<button class="guide-tab active" data-tab="metrics">Metrics</button>
					<button class="guide-tab" data-tab="efficiency">Efficiency Score</button>
					<button class="guide-tab" data-tab="charts">Charts</button>
					<button class="guide-tab" data-tab="tips">Analysis Tips</button>
				</div>

				<!-- METRICS TAB -->
				<div class="guide-tab-content active" data-content="metrics">
					<div class="metric-grid">
						<div class="metric-card">
							<div class="metric-card-header">
								<div class="metric-icon" style="background: #d3f9d8; color: #2f9e44;">$</div>
								<div>
									<div class="metric-card-title">Sales Metrics</div>
									<div class="metric-card-subtitle">Revenue tracking</div>
								</div>
							</div>
							<ul class="metric-list">
								<li><span class="metric-name">Gross Sales</span><span class="metric-formula">Total before deductions</span></li>
								<li><span class="metric-name">Returns</span><span class="metric-formula">Refunded amount</span></li>
								<li><span class="metric-name">Net Sales</span><span class="metric-formula">Gross - Returns</span></li>
								<li><span class="metric-name">Discounts</span><span class="metric-formula">Total discounts given</span></li>
							</ul>
						</div>

						<div class="metric-card">
							<div class="metric-card-header">
								<div class="metric-icon" style="background: #d0ebff; color: #1971c2;">#</div>
								<div>
									<div class="metric-card-title">Volume Metrics</div>
									<div class="metric-card-subtitle">Transaction counts</div>
								</div>
							</div>
							<ul class="metric-list">
								<li><span class="metric-name">Invoices</span><span class="metric-formula">Transaction count</span></li>
								<li><span class="metric-name">Items</span><span class="metric-formula">Qty sold</span></li>
								<li><span class="metric-name">Customers</span><span class="metric-formula">Unique customers</span></li>
							</ul>
						</div>

						<div class="metric-card">
							<div class="metric-card-header">
								<div class="metric-icon" style="background: #e5dbff; color: #7048e8;">⚡</div>
								<div>
									<div class="metric-card-title">Performance</div>
									<div class="metric-card-subtitle">Productivity measures</div>
								</div>
							</div>
							<ul class="metric-list">
								<li><span class="metric-name">Avg Ticket</span><span class="metric-formula">Gross ÷ Invoices</span></li>
								<li><span class="metric-name">Sales/Hr</span><span class="metric-formula">Gross ÷ Hours</span></li>
								<li><span class="metric-name">Inv/Hr</span><span class="metric-formula">Invoices ÷ Hours</span></li>
								<li><span class="metric-name">Peak Hour</span><span class="metric-formula">Busiest hour</span></li>
							</ul>
						</div>

						<div class="metric-card">
							<div class="metric-card-header">
								<div class="metric-icon" style="background: #ffe3e3; color: #e03131;">%</div>
								<div>
									<div class="metric-card-title">Rate Analysis</div>
									<div class="metric-card-subtitle">Percentage indicators</div>
								</div>
							</div>
							<ul class="metric-list">
								<li><span class="metric-name">Return %</span><span class="metric-formula">Returns ÷ Gross × 100</span></li>
								<li><span class="metric-name">Disc %</span><span class="metric-formula">Discounts ÷ Gross × 100</span></li>
							</ul>
						</div>

						<div class="metric-card">
							<div class="metric-card-header">
								<div class="metric-icon" style="background: #fff3bf; color: #f08c00;">💳</div>
								<div>
									<div class="metric-card-title">Payment Split</div>
									<div class="metric-card-subtitle">Payment methods</div>
								</div>
							</div>
							<ul class="metric-list">
								<li><span class="metric-name">Cash</span><span class="metric-formula">Cash payments total</span></li>
								<li><span class="metric-name">Non-Cash</span><span class="metric-formula">Card, mobile, etc.</span></li>
							</ul>
						</div>

						<div class="metric-card">
							<div class="metric-card-header">
								<div class="metric-icon" style="background: #c3fae8; color: #0ca678;">⏱</div>
								<div>
									<div class="metric-card-title">Shift Details</div>
									<div class="metric-card-subtitle">Time & identity</div>
								</div>
							</div>
							<ul class="metric-list">
								<li><span class="metric-name">Duration</span><span class="metric-formula">End - Start (hours)</span></li>
								<li><span class="metric-name">Cashier</span><span class="metric-formula">Shift operator</span></li>
								<li><span class="metric-name">POS Profile</span><span class="metric-formula">Terminal/Location</span></li>
							</ul>
						</div>
					</div>
				</div>

				<!-- EFFICIENCY TAB -->
				<div class="guide-tab-content" data-content="efficiency">
					<div class="efficiency-breakdown">
						<div class="efficiency-base">
							<div class="efficiency-base-number">70</div>
							<div class="efficiency-base-label">Base Score (Starting Point)</div>
						</div>

						<div class="factor-grid">
							<div class="factor-card">
								<div class="factor-title">📉 Return Rate Impact</div>
								<div class="factor-row">
									<span class="factor-condition">≤ 5% returns</span>
									<span class="factor-points positive">+5 pts</span>
								</div>
								<div class="factor-row">
									<span class="factor-condition">> 15% returns</span>
									<span class="factor-points negative">up to -20 pts</span>
								</div>
							</div>

							<div class="factor-card">
								<div class="factor-title">🏷️ Discount Rate Impact</div>
								<div class="factor-row">
									<span class="factor-condition">≤ 5% discounts</span>
									<span class="factor-points positive">+5 pts</span>
								</div>
								<div class="factor-row">
									<span class="factor-condition">> 20% discounts</span>
									<span class="factor-points negative">up to -10 pts</span>
								</div>
							</div>

							<div class="factor-card">
								<div class="factor-title">🎫 Ticket Size vs Average</div>
								<div class="factor-row">
									<span class="factor-condition">≥ 50% above avg</span>
									<span class="factor-points positive">+10 pts</span>
								</div>
								<div class="factor-row">
									<span class="factor-condition">≥ 20% above avg</span>
									<span class="factor-points positive">+5 pts</span>
								</div>
								<div class="factor-row">
									<span class="factor-condition">< 30% below avg</span>
									<span class="factor-points negative">-5 pts</span>
								</div>
							</div>

							<div class="factor-card">
								<div class="factor-title">⚡ Transactions/Hr vs Average</div>
								<div class="factor-row">
									<span class="factor-condition">≥ 50% above avg</span>
									<span class="factor-points positive">+10 pts</span>
								</div>
								<div class="factor-row">
									<span class="factor-condition">≥ 20% above avg</span>
									<span class="factor-points positive">+5 pts</span>
								</div>
								<div class="factor-row">
									<span class="factor-condition">< 30% below avg</span>
									<span class="factor-points negative">-5 pts</span>
								</div>
							</div>
						</div>

						<div class="rating-scale">
							<div class="rating-badge" style="background: linear-gradient(135deg, #2f9e44, #40c057);">
								Excellent<span>90 - 100</span>
							</div>
							<div class="rating-badge" style="background: linear-gradient(135deg, #1971c2, #339af0);">
								Good<span>75 - 89</span>
							</div>
							<div class="rating-badge" style="background: linear-gradient(135deg, #f08c00, #fab005);">
								Average<span>60 - 74</span>
							</div>
							<div class="rating-badge" style="background: linear-gradient(135deg, #e03131, #ff6b6b);">
								Needs Work<span>Below 60</span>
							</div>
						</div>
					</div>
				</div>

				<!-- CHARTS TAB -->
				<div class="guide-tab-content" data-content="charts">
					<div class="chart-grid">
						<div class="chart-card">
							<div class="chart-card-title">📊 Shift Performance</div>
							<div class="chart-card-desc">Compare Net Sales and Efficiency across your most recent shifts. Bars show revenue, line shows efficiency trend.</div>
						</div>
						<div class="chart-card">
							<div class="chart-card-title">👥 Cashier Comparison</div>
							<div class="chart-card-desc">Rank your team by total sales and average efficiency. Identify top performers and coaching opportunities.</div>
						</div>
						<div class="chart-card">
							<div class="chart-card-title">🕐 Hourly Breakdown</div>
							<div class="chart-card-desc">Discover which hours generate the most sales. Perfect for staffing optimization and break scheduling.</div>
						</div>
						<div class="chart-card">
							<div class="chart-card-title">💳 Payment Methods</div>
							<div class="chart-card-desc">View the distribution of payment types. Track cash vs card trends for cash handling and reconciliation.</div>
						</div>
						<div class="chart-card">
							<div class="chart-card-title">📈 Daily Trend</div>
							<div class="chart-card-desc">Track daily sales with a 3-day moving average. Spot patterns, seasonality, and growth trends.</div>
						</div>
					</div>
				</div>

				<!-- TIPS TAB -->
				<div class="guide-tab-content" data-content="tips">
					<ul class="tip-list">
						<li class="tip-item">
							<div class="tip-icon">🔴</div>
							<div class="tip-content">
								<div class="tip-title">High Return Rate (>10%)</div>
								<div class="tip-desc">May indicate product quality issues, incorrect item selection at POS, or need for staff training on product knowledge.</div>
							</div>
						</li>
						<li class="tip-item">
							<div class="tip-icon">🐢</div>
							<div class="tip-content">
								<div class="tip-title">Low Transactions per Hour</div>
								<div class="tip-desc">During peak hours, this suggests staffing shortages or process bottlenecks. Review queue management and checkout procedures.</div>
							</div>
						</li>
						<li class="tip-item">
							<div class="tip-icon">📊</div>
							<div class="tip-content">
								<div class="tip-title">Compare Avg Ticket by Cashier</div>
								<div class="tip-desc">Higher tickets may indicate better upselling skills. Use top performers to train others on suggestive selling techniques.</div>
							</div>
						</li>
						<li class="tip-item">
							<div class="tip-icon">⏰</div>
							<div class="tip-content">
								<div class="tip-title">Use Peak Hour Data</div>
								<div class="tip-desc">Schedule your best performers during peak hours. Align breaks and shift changes with slower periods.</div>
							</div>
						</li>
						<li class="tip-item">
							<div class="tip-icon">🏷️</div>
							<div class="tip-content">
								<div class="tip-title">Monitor Discount Patterns</div>
								<div class="tip-desc">Consistently high discounts from specific cashiers may indicate unauthorized discounting or need for price override controls.</div>
							</div>
						</li>
					</ul>
				</div>
			</div>
		`;
	},

	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -30)
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today()
		},
		{
			fieldname: "pos_profile",
			label: __("POS Profile"),
			fieldtype: "Link",
			options: "POS Profile"
		},
		{
			fieldname: "cashier",
			label: __("Cashier"),
			fieldtype: "Link",
			options: "User"
		},
		{
			fieldname: "sales_person",
			label: __("Sales Person"),
			fieldtype: "Link",
			options: "Sales Person"
		},
		{
			fieldname: "shift",
			label: __("Shift"),
			fieldtype: "Link",
			options: "POS Closing Shift"
		},
		{
			fieldname: "chart_type",
			label: __("Chart View"),
			fieldtype: "Select",
			options: "Shift Performance\nCashier Comparison\nHourly Breakdown\nPayment Methods\nDaily Trend",
			default: "Shift Performance",
			on_change: function() {
				frappe.query_report.refresh();
			}
		}
	],

	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		// Rating colors
		if (column.fieldname === "rating" && data.rating) {
			const colors = {
				"Excellent": "#28a745",
				"Good": "#17a2b8",
				"Average": "#ffc107",
				"Needs Improvement": "#dc3545"
			};
			const color = colors[data.rating] || "#6c757d";
			value = `<span style="color: ${color}; font-weight: 600;">${value}</span>`;
		}

		// Efficiency colors
		if (column.fieldname === "efficiency" && data.efficiency !== undefined) {
			let color = "#dc3545";
			if (data.efficiency >= 90) color = "#28a745";
			else if (data.efficiency >= 75) color = "#17a2b8";
			else if (data.efficiency >= 60) color = "#ffc107";
			value = `<span style="color: ${color}; font-weight: 600;">${value}</span>`;
		}

		// Returns in red
		if (column.fieldname === "returns" && data.returns > 0) {
			value = `<span style="color: #dc3545;">${value}</span>`;
		}

		// Return rate warning
		if (column.fieldname === "return_rate" && data.return_rate > 10) {
			value = `<span style="color: #dc3545; font-weight: 500;">${value}</span>`;
		}

		// Peak hour highlight
		if (column.fieldname === "peak_hour" && data.peak_hour) {
			value = `<span style="background: #e3f2fd; padding: 2px 8px; border-radius: 4px;">${value}</span>`;
		}

		// Sales person highlight
		if (column.fieldname === "sales_person" && data.sales_person) {
			value = `<span style="background: #fff3e0; padding: 2px 8px; border-radius: 4px;">${value}</span>`;
		}

		return value;
	},

	after_datatable_render: function() {
		const chart_type = frappe.query_report.get_filter_value("chart_type");
		if (chart_type && chart_type !== "Shift Performance") {
			this.render_custom_chart(chart_type);
		}
	},

	render_custom_chart: function(chart_type) {
		const filters = frappe.query_report.get_filter_values();
		const method_base = "pos_next.pos_next.report.sales_vs_shifts_report.sales_vs_shifts_report";
		// Filter out Total/summary rows once for all charts
		const result = (frappe.query_report.data || []).filter(d => d.shift_id && d.shift_id !== "Total");

		if (chart_type === "Cashier Comparison") {
			// Aggregate by cashier
			const cashierData = {};
			result.forEach(d => {
				const cashier = d.cashier || d.cashier_id || "Unknown";
				if (!cashierData[cashier]) {
					cashierData[cashier] = { sales: 0, invoices: 0, shifts: 0, efficiency: 0 };
				}
				cashierData[cashier].sales += parseFloat(d.net_sales) || 0;
				cashierData[cashier].invoices += parseInt(d.invoices) || 0;
				cashierData[cashier].shifts += 1;
				cashierData[cashier].efficiency += parseFloat(d.efficiency) || 0;
			});

			// Sort by sales descending
			const sorted = Object.entries(cashierData)
				.map(([name, data]) => ({
					name: name.split(' ')[0], // First name only
					sales: data.sales || 0,
					invoices: data.invoices || 0,
					avgEfficiency: data.shifts > 0 ? Math.round(data.efficiency / data.shifts) : 0
				}))
				.sort((a, b) => b.sales - a.sales)
				.slice(0, 10);

			// Don't render if no data or less than 2 points (line chart needs 2+ points)
			if (sorted.length < 2) {
				return;
			}

			frappe.query_report.render_chart({
				data: {
					labels: sorted.map(d => d.name),
					datasets: [
						{ name: __("Net Sales"), values: sorted.map(d => d.sales), chartType: "bar" },
						{ name: __("Avg Efficiency %"), values: sorted.map(d => d.avgEfficiency), chartType: "line" }
					]
				},
				type: "axis-mixed",
				colors: ["#28a745", "#5e64ff"],
				height: 300,
				barOptions: { spaceRatio: 0.4 }
			});
		}

		else if (chart_type === "Hourly Breakdown") {
			frappe.call({
				method: `${method_base}.get_hourly_breakdown`,
				args: { filters },
				callback: (r) => {
					if (!r.message || !r.message.length) return;

					const labels = [];
					const sales = [];
					const invoices = [];

					// Only show hours with data, or business hours (6 AM - 11 PM)
					for (let i = 6; i <= 23; i++) {
						// Simple hour format: 6, 7, 8... 12, 13... 23
						const hourLabel = i <= 12 ? `${i}${i < 12 ? 'am' : 'pm'}` : `${i - 12}pm`;
						labels.push(hourLabel);
						const hourData = r.message.find(d => d.hour === i);
						sales.push(hourData ? hourData.total_sales : 0);
						invoices.push(hourData ? hourData.invoice_count : 0);
					}

					frappe.query_report.render_chart({
						data: {
							labels,
							datasets: [
								{ name: __("Sales"), values: sales, chartType: "bar" },
								{ name: __("Invoices"), values: invoices, chartType: "line" }
							]
						},
						type: "axis-mixed",
						colors: ["#28a745", "#5e64ff"],
						height: 320,
						barOptions: { spaceRatio: 0.5 },
						axisOptions: {
							xAxisMode: "tick",
							xIsSeries: false
						}
					});
				}
			});
		}

		else if (chart_type === "Payment Methods") {
			frappe.call({
				method: `${method_base}.get_payment_method_breakdown`,
				args: { filters },
				callback: (r) => {
					if (!r.message || !r.message.length) return;

					const total = r.message.reduce((sum, d) => sum + d.total_amount, 0);
					const sorted = r.message.sort((a, b) => b.total_amount - a.total_amount);

					// Short labels for pie chart - just percentage
					const labels = sorted.map(d => {
						const pct = Math.round(d.total_amount / total * 100);
						// Truncate long payment method names
						const name = d.mode_of_payment.length > 10
							? d.mode_of_payment.substring(0, 10) + '..'
							: d.mode_of_payment;
						return `${name} ${pct}%`;
					});

					frappe.query_report.render_chart({
						data: {
							labels: labels,
							datasets: [{ name: __("Amount"), values: sorted.map(d => d.total_amount) }]
						},
						type: "pie",
						colors: ["#28a745", "#5e64ff", "#ffc107", "#17a2b8", "#dc3545", "#6f42c1", "#fd7e14", "#20c997"],
						height: 360
					});
				}
			});
		}

		else if (chart_type === "Daily Trend") {
			frappe.call({
				method: `${method_base}.get_daily_trend`,
				args: { filters },
				callback: (r) => {
					if (!r.message || !r.message.length) return;

					// Calculate moving average (3-day)
					const sales = r.message.map(d => d.total_sales);
					const movingAvg = sales.map((val, i, arr) => {
						if (i < 2) return val;
						return Math.round((arr[i-2] + arr[i-1] + val) / 3);
					});

					frappe.query_report.render_chart({
						data: {
							labels: r.message.map(d => {
								const date = new Date(d.date);
								return date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
							}),
							datasets: [
								{ name: __("Daily Sales"), values: sales, chartType: "bar" },
								{ name: __("3-Day Avg"), values: movingAvg, chartType: "line" }
							]
						},
						type: "axis-mixed",
						colors: ["#28a745", "#dc3545"],
						height: 300,
						lineOptions: { dotSize: 3 },
						barOptions: { spaceRatio: 0.4 }
					});
				}
			});
		}
	},

	get_chart_data: function(columns, result) {
		const chart_type = frappe.query_report.get_filter_value("chart_type");

		// Custom charts are rendered via after_datatable_render
		if (chart_type && chart_type !== "Shift Performance") {
			return null;
		}

		if (!result || !result.length) {
			return null;
		}

		// Filter out summary rows and rows without dates, then sort and take recent 15
		const sorted = [...result]
			.filter(d => d.shift_date && d.shift_id && d.shift_id !== "Total")
			.sort((a, b) => new Date(a.shift_date) - new Date(b.shift_date))
			.slice(-15);

		if (!sorted.length) {
			return null;
		}

		// Ensure all values are valid numbers
		const netSalesValues = sorted.map(d => parseFloat(d.net_sales) || 0);
		const efficiencyValues = sorted.map(d => parseFloat(d.efficiency) || 0);

		// Don't render chart if all values are zero/invalid
		if (!netSalesValues.some(v => v > 0) && !efficiencyValues.some(v => v > 0)) {
			return null;
		}

		// Build labels: Short date format
		const labels = sorted.map(d => {
			const date = new Date(d.shift_date);
			return date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
		});

		// For single data point, use bar chart only (line chart needs 2+ points)
		if (sorted.length === 1) {
			return {
				data: {
					labels,
					datasets: [
						{
							name: __("Net Sales"),
							values: netSalesValues
						}
					]
				},
				type: "bar",
				colors: ["#10b981"],
				height: 280
			};
		}

		// For multiple data points, use mixed chart
		return {
			data: {
				labels,
				datasets: [
					{
						name: __("Net Sales"),
						values: netSalesValues,
						chartType: "bar"
					},
					{
						name: __("Efficiency %"),
						values: efficiencyValues,
						chartType: "line"
					}
				]
			},
			type: "axis-mixed",
			colors: ["#10b981", "#6366f1"],
			height: 280,
			axisOptions: {
				xIsSeries: true,
				xAxisMode: "tick"
			},
			barOptions: {
				spaceRatio: 0.5
			},
			lineOptions: {
				dotSize: 6,
				regionFill: 1
			}
		};
	}
};
