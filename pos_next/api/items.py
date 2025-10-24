# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

import json
import re
from collections import defaultdict

import frappe
from erpnext.stock.doctype.batch.batch import get_batch_qty
from erpnext.stock.get_item_details import get_item_details as erpnext_get_item_details
from frappe import _, as_json
from frappe.utils import flt, nowdate

ITEM_RESULT_FIELDS = [
	"name as item_code",
	"item_name",
	"description",
	"stock_uom",
	"image",
	"is_stock_item",
	"has_batch_no",
	"has_serial_no",
	"item_group",
	"brand",
	"has_variants",
	"custom_company",
]

ITEM_RESULT_COLUMNS = ",\n\t".join(ITEM_RESULT_FIELDS)


def get_stock_availability(item_code, warehouse):
	"""Return total available quantity for an item in the given warehouse."""
	if not warehouse:
		return 0.0

	warehouses = [warehouse]
	if frappe.db.get_value("Warehouse", warehouse, "is_group"):
		# Include all child warehouses when a group warehouse is set
		warehouses = frappe.db.get_descendants("Warehouse", warehouse) or []

	rows = frappe.get_all(
		"Bin",
		fields=["sum(actual_qty) as actual_qty"],
		filters={"item_code": item_code, "warehouse": ["in", warehouses]},
	)

	return flt(rows[0].actual_qty) if rows else 0.0


def get_item_detail(item, doc=None, warehouse=None, price_list=None, company=None):
	"""Get item detail with batch/serial data and pricing"""
	item = json.loads(item) if isinstance(item, str) else item
	today = nowdate()
	item_code = item.get("item_code")
	batch_no_data = []
	serial_no_data = []

	if warehouse and item.get("has_batch_no"):
		batch_list = get_batch_qty(warehouse=warehouse, item_code=item_code)
		if batch_list:
			for batch in batch_list:
				if batch.qty > 0 and batch.batch_no:
					batch_doc = frappe.get_cached_doc("Batch", batch.batch_no)
					if (
						str(batch_doc.expiry_date) > str(today) or batch_doc.expiry_date in ["", None]
					) and batch_doc.disabled == 0:
						batch_no_data.append(
							{
								"batch_no": batch.batch_no,
								"batch_qty": batch.qty,
								"expiry_date": batch_doc.expiry_date,
								"manufacturing_date": batch_doc.manufacturing_date,
							}
						)

	if warehouse and item.get("has_serial_no"):
		serial_no_data = frappe.get_all(
			"Serial No",
			filters={
				"item_code": item_code,
				"status": "Active",
				"warehouse": warehouse,
			},
			fields=["name as serial_no"],
		)

	item["selling_price_list"] = price_list

	# Handle multi-currency
	if company:
		company_currency = frappe.db.get_value("Company", company, "default_currency")
		price_list_currency = company_currency
		if price_list:
			price_list_currency = (
				frappe.db.get_value("Price List", price_list, "currency") or company_currency
			)

		exchange_rate = 1
		if price_list_currency != company_currency:
			from erpnext.setup.utils import get_exchange_rate

			try:
				exchange_rate = get_exchange_rate(price_list_currency, company_currency, today)
			except Exception:
				frappe.log_error(
					f"Missing exchange rate from {price_list_currency} to {company_currency}",
					"POS Next",
				)

		item["price_list_currency"] = price_list_currency
		item["plc_conversion_rate"] = exchange_rate
		item["conversion_rate"] = exchange_rate

		if doc:
			doc.price_list_currency = price_list_currency
			doc.plc_conversion_rate = exchange_rate
			doc.conversion_rate = exchange_rate

	# Add company to the item args
	if company:
		item["company"] = company

	# Create a proper doc structure with company
	if not doc and company:
		doc = frappe._dict({"doctype": "Sales Invoice", "company": company})

	max_discount = frappe.get_value("Item", item_code, "max_discount")

	# Prepare args dict for get_item_details - only include necessary fields
	args = frappe._dict(
		{
			"doctype": "Sales Invoice",
			"item_code": item.get("item_code"),
			"company": item.get("company"),
			"qty": item.get("qty", 1),
			"uom": item.get("uom"),  # Include UOM to fetch correct price list rate
			"selling_price_list": item.get("selling_price_list"),
			"price_list_currency": item.get("price_list_currency"),
			"plc_conversion_rate": item.get("plc_conversion_rate"),
			"conversion_rate": item.get("conversion_rate"),
		}
	)

	res = erpnext_get_item_details(args, doc)

	if item.get("is_stock_item") and warehouse:
		res["actual_qty"] = get_stock_availability(item_code, warehouse)

	res["max_discount"] = max_discount
	res["batch_no_data"] = batch_no_data
	res["serial_no_data"] = serial_no_data

	# Add item_group and brand for offer eligibility checking
	item_group, brand = frappe.db.get_value("Item", item_code, ["item_group", "brand"])
	res["item_group"] = item_group
	res["brand"] = brand

	# Add UOMs data
	uoms = frappe.get_all(
		"UOM Conversion Detail",
		filters={"parent": item_code},
		fields=["uom", "conversion_factor"],
	)

	# Add stock UOM if not already in uoms list
	stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
	if stock_uom:
		stock_uom_exists = False
		for uom_data in uoms:
			if uom_data.get("uom") == stock_uom:
				stock_uom_exists = True
				break

		if not stock_uom_exists:
			uoms.append({"uom": stock_uom, "conversion_factor": 1.0})

	res["item_uoms"] = uoms

	return res


@frappe.whitelist()
def search_by_barcode(barcode, pos_profile):
	"""Search item by barcode"""
	try:
		# Parse pos_profile if it's a JSON string
		if isinstance(pos_profile, str):
			try:
				pos_profile = json.loads(pos_profile)
			except (json.JSONDecodeError, ValueError):
				pass  # It's already a plain string

		# Ensure pos_profile is a string (handle dict or string input)
		if isinstance(pos_profile, dict):
			pos_profile = pos_profile.get("name") or pos_profile.get("pos_profile")

		if not pos_profile:
			frappe.throw(_("POS Profile is required"))

		# Search for item by barcode - also get UOM if barcode has specific UOM
		barcode_data = frappe.db.get_value(
			"Item Barcode", {"barcode": barcode}, ["parent", "uom"], as_dict=True
		)

		if barcode_data:
			item_code = barcode_data.parent
			barcode_uom = barcode_data.uom
		else:
			# Try searching in item code field directly
			item_code = frappe.db.get_value("Item", {"name": barcode})
			barcode_uom = None

		if not item_code:
			frappe.throw(_("Item with barcode {0} not found").format(barcode))

		# Get POS Profile details
		pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)

		# Validate POS Profile has required fields
		if not pos_profile_doc.warehouse:
			frappe.throw(_("Warehouse not set in POS Profile {0}").format(pos_profile))
		if not pos_profile_doc.selling_price_list:
			frappe.throw(_("Selling Price List not set in POS Profile {0}").format(pos_profile))
		if not pos_profile_doc.company:
			frappe.throw(_("Company not set in POS Profile {0}").format(pos_profile))

		# Get item doc
		item_doc = frappe.get_cached_doc("Item", item_code)

		# Check if item is allowed for sales
		if not item_doc.is_sales_item:
			frappe.throw(_("Item {0} is not allowed for sales").format(item_code))

		# Prepare item dict for get_item_detail
		item = {
			"item_code": item_code,
			"has_batch_no": item_doc.has_batch_no or 0,
			"has_serial_no": item_doc.has_serial_no or 0,
			"is_stock_item": item_doc.is_stock_item or 0,
			"pos_profile": pos_profile,
		}

		# Include UOM from barcode if available
		if barcode_uom:
			item["uom"] = barcode_uom

		# Get item details
		item_details = get_item_detail(
			item=json.dumps(item),
			warehouse=pos_profile_doc.warehouse,
			price_list=pos_profile_doc.selling_price_list,
			company=pos_profile_doc.company,
		)

		return item_details
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Search by Barcode Error")
		frappe.throw(_("Error searching by barcode: {0}").format(str(e)))


@frappe.whitelist()
def get_item_stock(item_code, warehouse):
	"""Get real-time stock for item"""
	try:
		from frappe.utils import flt

		# Get actual stock quantity
		stock_qty = (
			frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0
		)

		# Get reserved quantity
		reserved_qty = (
			frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "reserved_qty") or 0
		)

		available_qty = flt(stock_qty) - flt(reserved_qty)

		return {
			"item_code": item_code,
			"warehouse": warehouse,
			"stock_qty": flt(stock_qty),
			"reserved_qty": flt(reserved_qty),
			"available_qty": available_qty,
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Item Stock Error")
		frappe.throw(_("Error fetching item stock: {0}").format(str(e)))


@frappe.whitelist()
def get_batch_serial_details(item_code, warehouse):
	"""Get batch/serial number details"""
	try:
		# Check if item has batch
		has_batch_no = frappe.db.get_value("Item", item_code, "has_batch_no")
		# Check if item has serial
		has_serial_no = frappe.db.get_value("Item", item_code, "has_serial_no")

		result = {
			"item_code": item_code,
			"has_batch_no": has_batch_no,
			"has_serial_no": has_serial_no,
			"batches": [],
			"serial_nos": [],
		}

		if has_batch_no:
			# Get available batches (note: qty should come from get_batch_qty)
			batches = frappe.db.sql(
				"""
				SELECT batch_no, batch_qty as qty, expiry_date
				FROM `tabBatch`
				WHERE item = %s AND batch_qty > 0
				ORDER BY expiry_date ASC, creation ASC
				""",
				item_code,
				as_dict=1,
			)
			result["batches"] = batches

		if has_serial_no:
			# Get available serial numbers
			serial_nos = frappe.db.sql(
				"""
				SELECT name as serial_no, warehouse
				FROM `tabSerial No`
				WHERE item_code = %s AND warehouse = %s AND status = 'Active'
				ORDER BY creation ASC
				""",
				(item_code, warehouse),
				as_dict=1,
			)
			result["serial_nos"] = serial_nos

		return result
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Batch/Serial Details Error")
		frappe.throw(_("Error fetching batch/serial details: {0}").format(str(e)))


@frappe.whitelist()
def get_item_variants(template_item, pos_profile):
	"""Get all variants for a template item with prices and stock"""
	try:
		pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)

		# Get all variants of this template
		# Apply company filter: show variants for specific company + global variants (empty company)
		variant_filters = {"variant_of": template_item, "disabled": 0, "is_sales_item": 1}

		# Add company filter to show items for specific company + global items
		if pos_profile_doc.company:
			variant_filters["ifnull(custom_company, '')"] = ["in", [pos_profile_doc.company, ""]]

		variants = frappe.get_all(
			"Item",
			filters=variant_filters,
			fields=[
				"name as item_code",
				"item_name",
				"stock_uom",
				"image",
				"has_batch_no",
				"has_serial_no",
				"item_group",
				"brand",
				"custom_company",
			],
		)

		# If no variants found, return empty with helpful message
		if not variants:
			frappe.msgprint(
				_(f"No variants created for template item '{template_item}'. Please create variants first.")
			)
			return []

		# Get UOMs for all variants in a single query
		variant_codes = [v["item_code"] for v in variants]
		uom_map = {}
		if variant_codes:
			uoms = frappe.db.sql(
				"""
				SELECT parent, uom, conversion_factor
				FROM `tabUOM Conversion Detail`
				WHERE parent IN %s
				ORDER BY parent, idx
				""",
				[variant_codes],
				as_dict=1,
			)
			for uom in uoms:
				if uom["parent"] not in uom_map:
					uom_map[uom["parent"]] = []
				uom_map[uom["parent"]].append(
					{"uom": uom["uom"], "conversion_factor": uom["conversion_factor"]}
				)

		# Get all UOM-specific prices for variants
		uom_prices_map = {}
		if variant_codes:
			prices = frappe.db.sql(
				"""
				SELECT item_code, uom, price_list_rate
				FROM `tabItem Price`
				WHERE item_code IN %s AND price_list = %s
				ORDER BY item_code, uom
				""",
				[variant_codes, pos_profile_doc.selling_price_list],
				as_dict=1,
			)
			for price in prices:
				if price["item_code"] not in uom_prices_map:
					uom_prices_map[price["item_code"]] = {}
				uom_prices_map[price["item_code"]][price["uom"]] = price["price_list_rate"]

		# Get all variant attributes in a single query (performance optimization)
		attributes_map = {}
		if variant_codes:
			attributes = frappe.get_all(
				"Item Variant Attribute",
				filters={"parent": ["in", variant_codes]},
				fields=["parent", "attribute", "attribute_value"],
			)
			for attr in attributes:
				if attr["parent"] not in attributes_map:
					attributes_map[attr["parent"]] = {}
				attributes_map[attr["parent"]][attr["attribute"]] = attr["attribute_value"]

		# Batch query stock for all variants at once (performance optimization)
		stock_map = {}
		if variant_codes and pos_profile_doc.warehouse:
			stocks = frappe.db.sql(
				"""
				SELECT item_code, actual_qty
				FROM `tabBin`
				WHERE item_code IN %s AND warehouse = %s
				""",
				[variant_codes, pos_profile_doc.warehouse],
				as_dict=1,
			)
			stock_map = {s["item_code"]: s["actual_qty"] for s in stocks}

		# Enrich each variant with attributes, price, stock, and UOMs
		for variant in variants:
			# Get variant attributes from preloaded map
			variant["attributes"] = attributes_map.get(variant["item_code"], {})

			# Get price from preloaded map (check stock UOM first, then any UOM)
			variant_prices = uom_prices_map.get(variant["item_code"], {})
			price = variant_prices.get(variant["stock_uom"])
			if not price and variant_prices:
				# Fallback to first available price if stock UOM price not found
				price = next(iter(variant_prices.values()), None)
			variant["rate"] = price or 0

			# Get stock from pre-loaded stock map (performance optimization)
			variant["actual_qty"] = stock_map.get(variant["item_code"], 0)

			# Add warehouse
			variant["warehouse"] = pos_profile_doc.warehouse

			# Add UOMs (exclude stock UOM to avoid duplicates)
			all_uoms = uom_map.get(variant["item_code"], [])
			variant["item_uoms"] = [uom for uom in all_uoms if uom["uom"] != variant["stock_uom"]]

			# Add UOM-specific prices
			variant["uom_prices"] = uom_prices_map.get(variant["item_code"], {})

		return variants
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Item Variants Error")
		frappe.throw(_("Error fetching item variants: {0}").format(str(e)))


def _build_item_base_conditions(pos_profile_doc, item_group=None):
	"""Build reusable SQL conditions for POS item search."""
	conditions = [
		"disabled = 0",
		"is_sales_item = 1",
		"IFNULL(variant_of, '') = ''",
	]
	params = []

	if pos_profile_doc.company:
		conditions.append("(IFNULL(custom_company, '') IN (%s, ''))")
		params.append(pos_profile_doc.company)

	if item_group:
		conditions.append("item_group = %s")
		params.append(item_group)

	return conditions, params


@frappe.whitelist()
def get_items(pos_profile, search_term=None, item_group=None, start=0, limit=20):
	"""Get items for POS with stock, price, and tax details"""
	try:
		pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)

		filters = {
			"disabled": 0,
			"is_sales_item": 1,  # Only show items with "Allow Sales" enabled
			"ifnull(variant_of, '')": "",  # Exclude items that are variants of a template
		}

		# IMPORTANT: Filtering logic explained:
		# - Template items (has_variants=1) are shown → users select variants via dialog
		# - Regular items (has_variants=0, variant_of is null) are shown → direct add to cart
		# - Variant items (has_variants=0, variant_of is not null) are HIDDEN from main list

		# Add company filter - show items for specific company + global items (empty company)
		# Global items (custom_company is empty) are available to all companies
		if pos_profile_doc.company:
			filters["ifnull(custom_company, '')"] = ["in", [pos_profile_doc.company, ""]]

		# Add item group filter if provided
		if item_group:
			filters["item_group"] = item_group

		# Build search conditions with fuzzy word-order independent matching
		if search_term and len(search_term.strip()) > 0:
			# Split search term into words for fuzzy matching
			search_words = [word.strip() for word in search_term.split() if word.strip()]
			# Deduplicate to keep boolean queries lean and LIKE predicates minimal
			search_words = list(dict.fromkeys(search_words))

			def run_boolean_search():
				conditions, params = _build_item_base_conditions(pos_profile_doc, item_group)
				boolean_terms = []
				seen = set()

				for word in search_words:
					alnum_word = re.sub(r"[^\w]+", "", word)
					if not alnum_word:
						continue
					if alnum_word in seen:
						continue
					seen.add(alnum_word)
					if len(alnum_word) >= 3:
						boolean_terms.append(f"+{alnum_word}*")
					else:
						# Exact match for very short tokens
						boolean_terms.append(f'+"{alnum_word}"')

				if not boolean_terms:
					return []

				boolean_query = " ".join(boolean_terms[:8])  # limit tokens to keep MATCH performant
				conditions.append("MATCH(search_index) AGAINST (%s IN BOOLEAN MODE)")
				where_clause = " AND ".join(conditions)

				query = f"""
					SELECT
						{ITEM_RESULT_COLUMNS},
						MATCH(search_index) AGAINST (%s IN BOOLEAN MODE) AS relevance
					FROM `tabItem`
					WHERE {where_clause}
					ORDER BY relevance DESC, item_name ASC
					LIMIT %s OFFSET %s
				"""

				query_params = [boolean_query]
				query_params.extend(params)
				query_params.append(boolean_query)
				query_params.extend([limit, start])
				return frappe.db.sql(query, tuple(query_params), as_dict=1)

			def run_like_search():
				if not search_words:
					return []

				conditions, params = _build_item_base_conditions(pos_profile_doc, item_group)
				word_clauses = []
				for word in search_words:
					safe_word = frappe.db.escape_like(word)
					word_clauses.append("(name LIKE %s OR item_name LIKE %s OR description LIKE %s)")
					pattern = f"%{safe_word}%"
					params.extend([pattern, pattern, pattern])

				conditions.append(f"({' AND '.join(word_clauses)})")
				where_clause = " AND ".join(conditions)

				query = f"""
					SELECT
						{ITEM_RESULT_COLUMNS}
					FROM `tabItem`
					WHERE {where_clause}
					ORDER BY item_name ASC
					LIMIT %s OFFSET %s
				"""

				params.extend([limit, start])
				return frappe.db.sql(query, tuple(params), as_dict=1)

			items = run_boolean_search()
			if not items:
				items = run_like_search()
		else:
			# No search term - return all items with base filters
			items = frappe.get_list(
				"Item",
				filters=filters,
				fields=[
					"name as item_code",
					"item_name",
					"description",
					"stock_uom",
					"image",
					"is_stock_item",
					"has_batch_no",
					"has_serial_no",
					"item_group",
					"brand",
					"has_variants",
					"custom_company",
				],
				start=start,
				page_length=limit,
				order_by="item_name asc",
			)

		# Prepare maps for enrichment
		item_codes = [item["item_code"] for item in items]
		barcode_map = {}
		conversion_map = defaultdict(dict)  # parent -> {uom: factor}
		uom_map = {}  # parent -> [ {uom, conversion_factor}, ... ]
		uom_prices_map = {}  # item_code -> {uom: price_list_rate}

		# Barcodes
		if item_codes:
			barcodes = frappe.db.sql(
				"""
				SELECT parent, barcode
				FROM `tabItem Barcode`
				WHERE parent IN %s
				GROUP BY parent
				""",
				[item_codes],
				as_dict=1,
			)
			barcode_map = {b["parent"]: b["barcode"] for b in barcodes}

		# UOM conversions (both list & map for quick lookup)
		if item_codes:
			conversions = frappe.get_all(
				"UOM Conversion Detail",
				filters={"parent": ["in", item_codes]},
				fields=["parent", "uom", "conversion_factor"],
			)
			for row in conversions:
				# build list
				uom_map.setdefault(row.parent, []).append(
					{"uom": row.uom, "conversion_factor": row.conversion_factor}
				)
				# build fast lookup
				if row.uom:
					conversion_map[row.parent][row.uom] = row.conversion_factor

		# UOM-specific prices - batch query ALL prices for all items
		if item_codes:
			prices = frappe.db.sql(
				"""
				SELECT item_code, uom, price_list_rate
				FROM `tabItem Price`
				WHERE item_code IN %s AND price_list = %s
				ORDER BY item_code, uom
				""",
				[item_codes, pos_profile_doc.selling_price_list],
				as_dict=1,
			)
			for price in prices:
				uom_prices_map.setdefault(price["item_code"], {})[price["uom"]] = price["price_list_rate"]

		# Batch query stock for all items at once (performance optimization)
		stock_map = {}
		if item_codes and pos_profile_doc.warehouse:
			stock_items = [item["item_code"] for item in items if item.get("is_stock_item")]
			if stock_items:
				stocks = frappe.db.sql(
					"""
					SELECT item_code, actual_qty
					FROM `tabBin`
					WHERE item_code IN %s AND warehouse = %s
					""",
					[stock_items, pos_profile_doc.warehouse],
					as_dict=1,
				)
				stock_map = {s["item_code"]: s["actual_qty"] for s in stocks}

		# Enrich items with price, stock, barcode, and UOM data
		for item in items:
			stock_uom = item.get("stock_uom")

			# Use pre-loaded price map instead of per-item queries
			price_row = None
			item_prices = uom_prices_map.get(item["item_code"], {})

			# 1) Try price explicitly for stock UOM (preferred)
			if stock_uom and stock_uom in item_prices:
				price_row = {"price_list_rate": item_prices[stock_uom], "uom": stock_uom}

			# 2) If not found, try any price for the item (and capture its UOM)
			elif item_prices:
				# Get first available price
				first_uom = next(iter(item_prices.keys()))
				price_row = {"price_list_rate": item_prices[first_uom], "uom": first_uom}

			# 3) If still not found and it's a template, derive min variant price
			derived_price = None
			if not price_row and item.get("has_variants"):
				variant_prices = frappe.db.sql(
					"""
					SELECT MIN(ip.price_list_rate) as min_price
					FROM `tabItem Price` ip
					INNER JOIN `tabItem` i ON i.name = ip.item_code
					WHERE i.variant_of = %s
					AND ip.price_list = %s
					AND i.disabled = 0
					""",
					[item["item_code"], pos_profile_doc.selling_price_list],
					as_dict=1,
				)
				derived_price = (
					variant_prices[0]["min_price"]
					if variant_prices and variant_prices[0].get("min_price")
					else None
				)

			# Finalize display price & display UOM
			display_rate = 0.0
			display_uom = stock_uom

			if price_row:
				raw_rate = flt(price_row.get("price_list_rate") or 0)
				price_uom = price_row.get("uom") or stock_uom
				if price_uom and stock_uom and price_uom != stock_uom:
					# convert to per-stock-UOM if possible
					cf = flt(conversion_map[item["item_code"]].get(price_uom) or 0)
					if cf:
						display_rate = raw_rate / cf
						display_uom = stock_uom
					else:
						# no conversion available: show as is (price UOM)
						display_rate = raw_rate
						display_uom = price_uom
				else:
					display_rate = raw_rate
					display_uom = stock_uom
			elif derived_price is not None:
				display_rate = flt(derived_price)
				display_uom = stock_uom

			item["rate"] = display_rate
			item["price_list_rate"] = display_rate
			item["uom"] = display_uom
			item["price_uom"] = display_uom
			item["conversion_factor"] = 1
			item["price_list_rate_price_uom"] = display_rate

			# Stock - use pre-loaded stock map (performance optimization)
			item["actual_qty"] = stock_map.get(item["item_code"], 0) if item.get("is_stock_item") else 0

			# Add warehouse to item (needed for stock validation)
			item["warehouse"] = pos_profile_doc.warehouse

			# Barcode
			item["barcode"] = barcode_map.get(item["item_code"], "")

			# Item UOMs (exclude stock UOM to avoid duplicates)
			all_uoms = uom_map.get(item["item_code"], []) or []
			item["item_uoms"] = [u for u in all_uoms if u.get("uom") != stock_uom]

			# UOM-specific prices map for frontend selector
			item["uom_prices"] = uom_prices_map.get(item["item_code"], {})

		return items
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Items Error")
		frappe.throw(_("Error fetching items: {0}").format(str(e)))


@frappe.whitelist()
def get_item_details(item_code, pos_profile, customer=None, qty=1, uom=None):
	"""Get detailed item info including price, tax, stock"""
	try:
		# Parse pos_profile if it's a JSON string
		if isinstance(pos_profile, str):
			try:
				pos_profile = json.loads(pos_profile)
			except (json.JSONDecodeError, ValueError):
				pass  # It's already a plain string

		# Ensure pos_profile is a string (handle dict or string input)
		if isinstance(pos_profile, dict):
			pos_profile = pos_profile.get("name") or pos_profile.get("pos_profile")

		if not pos_profile:
			frappe.throw(_("POS Profile is required"))

		pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
		item_doc = frappe.get_cached_doc("Item", item_code)

		# Check if item is allowed for sales
		if not item_doc.is_sales_item:
			frappe.throw(_("Item {0} is not allowed for sales").format(item_code))

		# Prepare item dict
		item = {
			"item_code": item_code,
			"has_batch_no": item_doc.has_batch_no,
			"has_serial_no": item_doc.has_serial_no,
			"is_stock_item": item_doc.is_stock_item,
			"pos_profile": pos_profile,
			"qty": qty,
		}

		# Include UOM if provided to fetch correct price list rate
		if uom:
			item["uom"] = uom

		return get_item_detail(
			item=json.dumps(item),
			warehouse=pos_profile_doc.warehouse,
			price_list=pos_profile_doc.selling_price_list,
			company=pos_profile_doc.company,
		)
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Item Details Error")
		frappe.throw(_("Error fetching item details: {0}").format(str(e)))


@frappe.whitelist()
def get_item_groups(pos_profile):
	"""Get item groups for filtering"""
	try:
		# Get item groups from POS Profile's item groups table
		item_groups = frappe.db.sql(
			"""
			SELECT DISTINCT ig.item_group
			FROM `tabPOS Item Group` ig
			WHERE ig.parent = %s
			ORDER BY ig.item_group
			""",
			pos_profile,
			as_dict=1,
		)

		# If no item groups defined in POS Profile, get all item groups
		if not item_groups:
			item_groups = frappe.get_list(
				"Item Group",
				filters={"is_group": 0},
				fields=["name as item_group"],
				order_by="name",
				limit_page_length=50,
			)

		return item_groups
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Item Groups Error")
		frappe.throw(_("Error fetching item groups: {0}").format(str(e)))


@frappe.whitelist()
def get_stock_quantities(item_codes, warehouse):
	"""
	Lightweight endpoint to get only stock quantities for specified items.
	Used for real-time stock updates after invoice submission.

	Args:
		item_codes: JSON string or list of item codes
		warehouse: Warehouse name

	Returns:
		List of dicts with item_code, warehouse, and actual_qty
	"""
	try:
		# Parse item_codes if it's a JSON string
		if isinstance(item_codes, str):
			try:
				item_codes = json.loads(item_codes)
			except (json.JSONDecodeError, ValueError):
				item_codes = [item_codes]

		if not item_codes or not warehouse:
			return []

		# Normalize input: accept any iterable, drop falsy values, keep order while deduplicating
		if not isinstance(item_codes, list | tuple | set):
			item_codes = [item_codes]

		normalized_codes = []
		seen = set()
		for code in item_codes:
			clean_code = (code or "").strip() if isinstance(code, str) else code
			if not clean_code or clean_code in seen:
				continue
			seen.add(clean_code)
			normalized_codes.append(clean_code)

		if not normalized_codes:
			return []

		# Support group warehouses by expanding to leaf warehouses
		warehouses = [warehouse]
		if frappe.db.get_value("Warehouse", warehouse, "is_group"):
			child_warehouses = frappe.db.get_descendants("Warehouse", warehouse) or []
			# Fallback to original warehouse if no children are returned
			warehouses = child_warehouses or [warehouse]

		if not warehouses:
			return []

		# Batch query for stock quantities across all relevant warehouses
		stock_rows = frappe.db.sql(
			"""
			SELECT
				item_code,
				COALESCE(SUM(actual_qty), 0) AS actual_qty,
				COALESCE(SUM(reserved_qty), 0) AS reserved_qty
			FROM `tabBin`
			WHERE item_code IN %(item_codes)s
			AND warehouse IN %(warehouses)s
			GROUP BY item_code
			""",
			{
				"item_codes": tuple(normalized_codes),
				"warehouses": tuple(warehouses),
			},
			as_dict=1,
		)

		# Create a lookup for items that have stock entries
		stock_lookup = {row["item_code"]: row for row in stock_rows}

		# Return stock for all requested items (0 if not in Bin table)
		result = []
		for item_code in normalized_codes:
			row = stock_lookup.get(item_code)
			actual_qty = flt(row["actual_qty"]) if row else 0.0
			reserved_qty = flt(row["reserved_qty"]) if row else 0.0
			result.append(
				{
					"item_code": item_code,
					"warehouse": warehouse,
					"actual_qty": actual_qty,
					"stock_qty": actual_qty,  # Alias for frontend convenience
					"reserved_qty": reserved_qty,
					"available_qty": actual_qty - reserved_qty,
				}
			)

		return result

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Stock Quantities Error")
		frappe.throw(_("Error fetching stock quantities: {0}").format(str(e)))
