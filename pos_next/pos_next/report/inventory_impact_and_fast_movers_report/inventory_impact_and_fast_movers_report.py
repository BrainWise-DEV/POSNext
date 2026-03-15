# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, cint


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart_data(data)
	return columns, data, None, chart


def get_columns():
	"""Return columns for the report"""
	return [
		{
			"fieldname": "item_code",
			"label": _("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 130
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 200
		},
		{
			"fieldname": "item_group",
			"label": _("Item Group"),
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 130
		},
		{
			"fieldname": "qty_sold",
			"label": _("Qty Sold"),
			"fieldtype": "Float",
			"width": 100
		},
		{
			"fieldname": "total_sales_value",
			"label": _("Sales Value"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "avg_selling_rate",
			"label": _("Avg Rate"),
			"fieldtype": "Currency",
			"width": 110
		},
		{
			"fieldname": "current_stock",
			"label": _("Current Stock"),
			"fieldtype": "Float",
			"width": 120
		},
		{
			"fieldname": "days_to_stockout",
			"label": _("Days to Stockout"),
			"fieldtype": "Int",
			"width": 140
		},
		{
			"fieldname": "stock_depletion_rate",
			"label": _("Depletion Rate/Day"),
			"fieldtype": "Float",
			"width": 150
		},
		{
			"fieldname": "stock_status",
			"label": _("Stock Status"),
			"fieldtype": "Data",
			"width": 120
		},
		{
			"fieldname": "velocity_rank",
			"label": _("Velocity Rank"),
			"fieldtype": "Data",
			"width": 120
		},
		{
			"fieldname": "reorder_level",
			"label": _("Reorder Level"),
			"fieldtype": "Float",
			"width": 120
		}
	]


def get_data(filters):
	"""Get inventory impact and fast movers data.

	Stock is read from the POS Profile's warehouse so that depletion
	metrics reflect the actual location that serves this POS counter.
	"""
	conditions = get_conditions(filters)

	# Get warehouse from POS Profile if provided
	warehouse = None
	if filters.get("pos_profile"):
		warehouse = frappe.db.get_value("POS Profile", filters.get("pos_profile"), "warehouse")

	# Calculate date range for depletion rate
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")

	if from_date and to_date:
		from frappe.utils import date_diff
		date_range_days = max(date_diff(to_date, from_date), 1)
	else:
		date_range_days = 30  # Default to 30 days

	# Query to get item sales data
	query = """
		SELECT
			sii.item_code,
			sii.item_name,
			i.item_group,
			SUM(sii.qty) as qty_sold,
			SUM(sii.amount) as total_sales_value,
			AVG(sii.rate) as avg_selling_rate,
			i.min_order_qty as reorder_level
		FROM
			`tabSales Invoice Item` sii
		INNER JOIN
			`tabSales Invoice` si ON si.name = sii.parent
		INNER JOIN
			`tabItem` i ON i.name = sii.item_code
		WHERE
			si.docstatus = 1
			AND si.is_pos = 1
			AND si.is_return = 0
			{conditions}
		GROUP BY
			sii.item_code
		ORDER BY
			qty_sold DESC
	""".format(conditions=conditions)

	data = frappe.db.sql(query, filters, as_dict=1)

	# Include zero stock items (items with no sales in the period)
	if cint(filters.get("include_zero_stock")):
		sold_item_codes = {row.item_code for row in data}
		zero_stock_items = _get_zero_stock_items(filters, warehouse, sold_item_codes)
		data.extend(zero_stock_items)

	if not data:
		return []

	# Batch-fetch current stock levels (single query instead of N+1)
	item_codes = [row.item_code for row in data]
	stock_map = _get_stock_map(item_codes, warehouse)

	for row in data:
		row.current_stock = flt(stock_map.get(row.item_code, 0), 2)

		# Calculate stock depletion rate (qty sold per day)
		row.stock_depletion_rate = flt(row.qty_sold / date_range_days, 2)

		# Calculate days to stockout
		if row.stock_depletion_rate > 0:
			row.days_to_stockout = cint(row.current_stock / row.stock_depletion_rate)
		else:
			row.days_to_stockout = 999  # Effectively infinite

		# Determine stock status
		if row.current_stock <= 0:
			row.stock_status = "🔴 Out of Stock"
		elif row.days_to_stockout <= 7:
			row.stock_status = "🟠 Critical"
		elif row.days_to_stockout <= 14:
			row.stock_status = "🟡 Low"
		elif row.days_to_stockout <= 30:
			row.stock_status = "🟢 Good"
		else:
			row.stock_status = "🔵 Excess"

		# Set reorder level if not set
		if not row.reorder_level:
			# Suggest reorder level as 14 days of stock
			row.reorder_level = flt(row.stock_depletion_rate * 14, 2)

	# Filter by stock status if specified
	stock_status_filter = filters.get("stock_status")
	if stock_status_filter:
		data = [row for row in data if stock_status_filter in row.stock_status]

	# Assign velocity ranks based on quantity sold
	sorted_data = sorted(data, key=lambda x: x.qty_sold, reverse=True)
	# Only rank items that actually had sales
	sold_items = [row for row in sorted_data if row.qty_sold > 0]
	total_sold = len(sold_items)

	for idx, row in enumerate(sold_items):
		percentile = (idx + 1) / total_sold * 100

		if percentile <= 20:
			row.velocity_rank = "A - Fast Mover"
		elif percentile <= 50:
			row.velocity_rank = "B - Medium Mover"
		elif percentile <= 80:
			row.velocity_rank = "C - Slow Mover"
		else:
			row.velocity_rank = "D - Very Slow"

	# Items with no sales are always "D - Very Slow"
	for row in sorted_data:
		if row.qty_sold <= 0:
			row.velocity_rank = "D - Very Slow"

	return sorted_data


def _get_stock_map(item_codes, warehouse=None):
	"""Fetch current stock for all items in a single query.

	Returns dict {item_code: actual_qty}.
	When warehouse is specified, returns stock for that warehouse only.
	Otherwise sums across all warehouses.
	"""
	if not item_codes:
		return {}

	placeholders = ", ".join(["%s"] * len(item_codes))

	if warehouse:
		rows = frappe.db.sql("""
			SELECT item_code, actual_qty
			FROM `tabBin`
			WHERE item_code IN ({placeholders})
			AND warehouse = %s
		""".format(placeholders=placeholders), item_codes + [warehouse], as_dict=1)
	else:
		rows = frappe.db.sql("""
			SELECT item_code, SUM(actual_qty) as actual_qty
			FROM `tabBin`
			WHERE item_code IN ({placeholders})
			GROUP BY item_code
		""".format(placeholders=placeholders), item_codes, as_dict=1)

	return {row.item_code: flt(row.actual_qty) for row in rows}


def _get_zero_stock_items(filters, warehouse, sold_item_codes):
	"""Fetch items that had no sales in the period.

	Respects the POS Profile's allowed item groups when no explicit
	item_group filter is set.
	"""
	conditions = []
	params = {}

	if filters.get("item_group"):
		conditions.append("i.item_group = %(item_group)s")
		params["item_group"] = filters.get("item_group")
	elif filters.get("pos_profile"):
		allowed_groups = frappe.db.get_all(
			"POS Item Group",
			filters={"parent": filters.get("pos_profile"), "parenttype": "POS Profile"},
			pluck="item_group",
		)
		if allowed_groups:
			escaped = ", ".join([frappe.db.escape(g) for g in allowed_groups])
			conditions.append("i.item_group IN ({})".format(escaped))
		else:
			# No item groups configured — only include items that have a Bin
			# in the POS warehouse to avoid returning every item in the system
			conditions.append("b.item_code IS NOT NULL")

	warehouse_join = ""
	if warehouse:
		warehouse_join = "AND b.warehouse = %(warehouse)s"
		params["warehouse"] = warehouse

	where = (" AND " + " AND ".join(conditions)) if conditions else ""

	query = """
		SELECT
			i.item_code,
			i.item_name,
			i.item_group,
			0 as qty_sold,
			0 as total_sales_value,
			0 as avg_selling_rate,
			i.min_order_qty as reorder_level
		FROM
			`tabItem` i
		LEFT JOIN
			`tabBin` b ON b.item_code = i.name {warehouse_join}
		WHERE
			i.disabled = 0
			AND i.is_sales_item = 1
			AND i.has_variants = 0
			{where}
		GROUP BY
			i.item_code
	""".format(warehouse_join=warehouse_join, where=where)

	items = frappe.db.sql(query, params, as_dict=1)

	# Exclude items that already have sales data
	return [row for row in items if row.item_code not in sold_item_codes]


def get_conditions(filters):
	"""Build WHERE conditions"""
	conditions = []

	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")

	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")

	if filters.get("pos_profile"):
		conditions.append("si.pos_profile = %(pos_profile)s")

	if filters.get("shift"):
		conditions.append("""
			EXISTS (
				SELECT 1 FROM `tabSales Invoice Reference` sir
				WHERE sir.sales_invoice = si.name
				AND sir.parent = %(shift)s
				AND sir.parenttype = 'POS Closing Shift'
			)
		""")

	if filters.get("item_group"):
		conditions.append("i.item_group = %(item_group)s")

	return " AND " + " AND ".join(conditions) if conditions else ""


def get_chart_data(data):
	"""Generate chart for top movers"""
	if not data:
		return None

	# Top 15 fast movers
	top_movers = data[:15]

	return {
		"data": {
			"labels": [row.item_code for row in top_movers],
			"datasets": [
				{
					"name": "Quantity Sold",
					"values": [row.qty_sold for row in top_movers]
				}
			]
		},
		"type": "bar",
		"colors": ["#2196F3"],
		"barOptions": {
			"stacked": False
		}
	}
