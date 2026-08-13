# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt


def execute(filters=None):
	filters = filters or {}
	group_by_pos_profile = cint(filters.get("group_by_pos_profile"))
	columns = get_columns(group_by_pos_profile)
	data = get_data(filters, group_by_pos_profile)
	chart = get_chart_data(data, group_by_pos_profile)
	return columns, data, None, chart


def get_columns(group_by_pos_profile=0):
	"""Return columns for the report"""
	columns = []

	if group_by_pos_profile:
		columns.append(
			{
				"fieldname": "pos_profile",
				"label": _("POS Profile"),
				"fieldtype": "Link",
				"options": "POS Profile",
				"width": 150,
			}
		)

	columns.extend(
		[
			{
				"fieldname": "item_code",
				"label": _("Item Code"),
				"fieldtype": "Link",
				"options": "Item",
				"width": 130,
			},
			{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 200},
			{
				"fieldname": "item_group",
				"label": _("Item Group"),
				"fieldtype": "Link",
				"options": "Item Group",
				"width": 130,
			},
			{"fieldname": "qty_sold", "label": _("Qty Sold"), "fieldtype": "Float", "width": 100},
			{
				"fieldname": "total_sales_value",
				"label": _("Sales Value"),
				"fieldtype": "Currency",
				"width": 130,
			},
			{"fieldname": "avg_selling_rate", "label": _("Avg Rate"), "fieldtype": "Currency", "width": 110},
			{"fieldname": "current_stock", "label": _("Current Stock"), "fieldtype": "Float", "width": 120},
			{"fieldname": "days_to_stockout", "label": _("Days to Stockout"), "fieldtype": "Int", "width": 140},
			{
				"fieldname": "stock_depletion_rate",
				"label": _("Depletion Rate/Day"),
				"fieldtype": "Float",
				"width": 150,
			},
			{"fieldname": "stock_status", "label": _("Stock Status"), "fieldtype": "Data", "width": 120},
			{"fieldname": "velocity_rank", "label": _("Velocity Rank"), "fieldtype": "Data", "width": 120},
			{"fieldname": "reorder_level", "label": _("Reorder Level"), "fieldtype": "Float", "width": 120},
		]
	)

	return columns


def get_data(filters, group_by_pos_profile=0):
	"""Get inventory impact and fast movers data.

	Stock is read from the warehouse filter when set, otherwise from each
	POS Profile's warehouse so depletion metrics match the serving location.
	"""
	conditions = get_conditions(filters)

	warehouse = _resolve_warehouse(filters, group_by_pos_profile)

	# Calculate date range for depletion rate
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")

	if from_date and to_date:
		from frappe.utils import date_diff

		date_range_days = max(date_diff(to_date, from_date), 1)
	else:
		date_range_days = 30  # Default to 30 days

	pos_profile_select = "si.pos_profile," if group_by_pos_profile else ""
	group_by_clause = "sii.item_code, si.pos_profile" if group_by_pos_profile else "sii.item_code"

	query = f"""
		SELECT
			{pos_profile_select}
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
			{group_by_clause}
		ORDER BY
			qty_sold DESC
	"""

	data = frappe.db.sql(query, filters, as_dict=1)

	# Include zero stock items (items with no sales in the period)
	if cint(filters.get("include_zero_stock")):
		if group_by_pos_profile:
			sold_keys = {(row.item_code, row.pos_profile) for row in data}
		else:
			sold_keys = {row.item_code for row in data}
		zero_stock_items = _get_zero_stock_items(
			filters, warehouse, sold_keys, group_by_pos_profile
		)
		data.extend(zero_stock_items)

	if not data:
		return []

	_set_current_stock(data, filters, warehouse, group_by_pos_profile)

	for row in data:
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

	return _assign_velocity_ranks(data, group_by_pos_profile)


def _resolve_warehouse(filters, group_by_pos_profile):
	"""Warehouse used for stock when not grouping per POS Profile warehouse."""
	if filters.get("warehouse"):
		return filters.get("warehouse")

	# When grouping by POS Profile, stock is resolved per profile warehouse
	if group_by_pos_profile:
		return None

	if filters.get("pos_profile"):
		return frappe.db.get_value("POS Profile", filters.get("pos_profile"), "warehouse")

	return None


def _set_current_stock(data, filters, warehouse, group_by_pos_profile):
	"""Attach current_stock to each row.

	Grouped rows use the POS Profile warehouse unless a warehouse filter is set.
	Ungrouped rows use the resolved warehouse, or all warehouses combined.
	"""
	item_codes = list({row.item_code for row in data})

	if group_by_pos_profile and not filters.get("warehouse"):
		profile_names = list({row.pos_profile for row in data if row.pos_profile})
		profile_warehouse_map = _get_profile_warehouse_map(profile_names)
		warehouses = list({wh for wh in profile_warehouse_map.values() if wh})
		stock_map = _get_stock_map_by_warehouse(item_codes, warehouses)

		for row in data:
			wh = profile_warehouse_map.get(row.pos_profile)
			row.current_stock = flt(stock_map.get((row.item_code, wh), 0), 2)
		return

	stock_map = _get_stock_map(item_codes, warehouse)
	for row in data:
		row.current_stock = flt(stock_map.get(row.item_code, 0), 2)


def _get_profile_warehouse_map(profile_names):
	if not profile_names:
		return {}

	rows = frappe.db.get_all(
		"POS Profile",
		filters={"name": ["in", profile_names]},
		fields=["name", "warehouse"],
	)
	return {row.name: row.warehouse for row in rows}


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
		rows = frappe.db.sql(
			f"""
			SELECT item_code, actual_qty
			FROM `tabBin`
			WHERE item_code IN ({placeholders})
			AND warehouse = %s
		""",
			[*item_codes, warehouse],
			as_dict=1,
		)
	else:
		rows = frappe.db.sql(
			f"""
			SELECT item_code, SUM(actual_qty) as actual_qty
			FROM `tabBin`
			WHERE item_code IN ({placeholders})
			GROUP BY item_code
		""",
			item_codes,
			as_dict=1,
		)

	return {row.item_code: flt(row.actual_qty) for row in rows}


def _get_stock_map_by_warehouse(item_codes, warehouses):
	"""Fetch current stock keyed by (item_code, warehouse)."""
	if not item_codes or not warehouses:
		return {}

	item_placeholders = ", ".join(["%s"] * len(item_codes))
	wh_placeholders = ", ".join(["%s"] * len(warehouses))

	rows = frappe.db.sql(
		f"""
		SELECT item_code, warehouse, actual_qty
		FROM `tabBin`
		WHERE item_code IN ({item_placeholders})
		AND warehouse IN ({wh_placeholders})
	""",
		[*item_codes, *warehouses],
		as_dict=1,
	)

	return {(row.item_code, row.warehouse): flt(row.actual_qty) for row in rows}


def _get_zero_stock_items(filters, warehouse, sold_keys, group_by_pos_profile=0):
	"""Fetch items that had no sales in the period.

	Respects the POS Profile's allowed item groups when no explicit
	item_group filter is set.
	When grouping by POS Profile, returns one row per (item, pos_profile).
	"""
	if group_by_pos_profile:
		return _get_zero_stock_items_grouped(filters, sold_keys)

	conditions, params = _zero_stock_item_conditions(filters)
	return _query_zero_stock_items(conditions, params, warehouse, sold_keys)


def _get_zero_stock_items_grouped(filters, sold_keys):
	"""Zero-stock items as one row per POS Profile."""
	profiles = _get_pos_profiles_for_zero_stock(filters)
	rows = []

	for profile in profiles:
		profile_filters = dict(filters)
		profile_filters["pos_profile"] = profile.name
		warehouse = filters.get("warehouse") or profile.warehouse
		conditions, params = _zero_stock_item_conditions(profile_filters)
		items = _query_zero_stock_items(
			conditions,
			params,
			warehouse,
			sold_keys,
			pos_profile=profile.name,
		)
		rows.extend(items)

	return rows


def _get_pos_profiles_for_zero_stock(filters):
	profile_filters = {"disabled": 0}
	if filters.get("pos_profile"):
		profile_filters["name"] = filters.get("pos_profile")
	if filters.get("warehouse"):
		profile_filters["warehouse"] = filters.get("warehouse")

	return frappe.db.get_all("POS Profile", filters=profile_filters, fields=["name", "warehouse"])


def _zero_stock_item_conditions(filters):
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
			conditions.append(f"i.item_group IN ({escaped})")
		else:
			# No item groups configured — only include items that have a Bin
			# in the POS warehouse to avoid returning every item in the system
			conditions.append("b.item_code IS NOT NULL")

	return conditions, params


def _query_zero_stock_items(conditions, params, warehouse, sold_keys, pos_profile=None):
	warehouse_join = ""
	query_params = dict(params)
	if warehouse:
		warehouse_join = "AND b.warehouse = %(warehouse)s"
		query_params["warehouse"] = warehouse

	where = (" AND " + " AND ".join(conditions)) if conditions else ""

	query = f"""
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
	"""

	items = frappe.db.sql(query, query_params, as_dict=1)

	result = []
	for row in items:
		if pos_profile:
			row.pos_profile = pos_profile
			if (row.item_code, pos_profile) in sold_keys:
				continue
		elif row.item_code in sold_keys:
			continue
		result.append(row)

	return result


def get_conditions(filters):
	"""Build WHERE conditions"""
	conditions = []

	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")

	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")

	if filters.get("pos_profile"):
		conditions.append("si.pos_profile = %(pos_profile)s")

	if filters.get("warehouse"):
		conditions.append("sii.warehouse = %(warehouse)s")

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


def _assign_velocity_ranks(data, group_by_pos_profile):
	"""Assign velocity ranks based on quantity sold.

	When grouped by POS Profile, ranks are calculated within each profile.
	"""
	if group_by_pos_profile:
		grouped = defaultdict(list)
		for row in data:
			grouped[row.pos_profile].append(row)

		ranked = []
		for rows in grouped.values():
			ranked.extend(_rank_rows(rows))
		return ranked

	return _rank_rows(data)


def _rank_rows(data):
	sorted_data = sorted(data, key=lambda x: x.qty_sold, reverse=True)
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

	for row in sorted_data:
		if row.qty_sold <= 0:
			row.velocity_rank = "D - Very Slow"

	return sorted_data


def get_chart_data(data, group_by_pos_profile=0):
	"""Generate chart for top movers"""
	if not data:
		return None

	# Top 15 fast movers
	top_movers = data[:15]

	if group_by_pos_profile:
		labels = [f"{row.item_code} ({row.pos_profile or ''})" for row in top_movers]
	else:
		labels = [row.item_code for row in top_movers]

	return {
		"data": {
			"labels": labels,
			"datasets": [{"name": "Quantity Sold", "values": [row.qty_sold for row in top_movers]}],
		},
		"type": "bar",
		"colors": ["#2196F3"],
		"barOptions": {"stacked": False},
	}
