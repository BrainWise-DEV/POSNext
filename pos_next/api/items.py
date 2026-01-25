# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

import json
from collections import defaultdict

import frappe
from erpnext.stock.doctype.batch.batch import get_batch_qty
from erpnext.stock.get_item_details import get_item_details as erpnext_get_item_details
from frappe import _
from frappe.query_builder import DocType, functions as fn
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
	"disabled",
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
	"""
	Get comprehensive item details including batch/serial data, pricing, and stock information.

	This function enriches basic item data with real-time information needed for POS transactions:
	- Batch numbers with expiry dates (for batch-tracked items)
	- Serial numbers (for serial-tracked items)
	- Pricing with multi-currency support
	- UOM conversions
	- Stock availability
	- Item attributes (group, brand)

	Batch Tracking:
	===============
	For items with has_batch_no=1, returns all active batches with:
	- Available quantity per batch
	- Expiry dates (excludes expired batches)
	- Manufacturing dates
	- Only includes batches with qty > 0 and not disabled

	Serial Number Tracking:
	=======================
	For items with has_serial_no=1, returns all available serial numbers:
	- Only Active serial numbers
	- From specified warehouse only
	- Serial numbers are unique identifiers for individual units

	Multi-Currency Pricing:
	=======================
	Handles price lists in different currencies with automatic conversion:
	- Fetches exchange rates from price list currency to company currency
	- Applies conversion factors (plc_conversion_rate)
	- Falls back to 1:1 if exchange rate unavailable (with error logging)

	UOM (Unit of Measure) Handling:
	================================
	Returns all UOM conversions for the item:
	- Stock UOM (base unit)
	- Alternative UOMs with conversion factors
	- Example: Item sold in "Box" but stocked in "Pcs" (1 Box = 12 Pcs)

	Args:
		item (dict|str): Item data dict or JSON string with at least:
						 - item_code: Item identifier (required)
						 - has_batch_no: 1 if batch tracked
						 - has_serial_no: 1 if serial tracked
						 - qty: Quantity (default: 1)
		doc (frappe.Document, optional): Sales Invoice document for context
		warehouse (str, optional): Warehouse for stock/batch/serial lookup
		price_list (str, optional): Selling price list name
		company (str, optional): Company for currency conversion

	Returns:
		dict: Enriched item details containing:
			  - All ERPNext item_details (rate, tax, etc.)
			  - actual_qty: Stock available in warehouse
			  - batch_no_data: List of available batches with expiry dates
			  - serial_no_data: List of available serial numbers
			  - max_discount: Maximum discount allowed
			  - item_uoms: Alternative UOMs with conversion factors
			  - item_group, brand: For offer eligibility checking

	Example:
		>>> item = {
		... 	"item_code": "LAPTOP-001",
		... 	"has_serial_no": 1,
		... 	"qty": 1
		... }
		>>> details = get_item_detail(
		... 	item=json.dumps(item),
		... 	warehouse="Main Store",
		... 	price_list="Standard Selling",
		... 	company="My Company"
		... )
		>>> print(details["serial_no_data"])
		[{"serial_no": "SN001"}, {"serial_no": "SN002"}]

	Database Queries:
		- Batches: 1 query (only if has_batch_no=1)
		- Serial Numbers: 1 query (only if has_serial_no=1)
		- Item Details: 1 query via ERPNext's get_item_details
		- Stock: 1 query (only if is_stock_item=1)
		- UOMs: 1 query for conversion details
		Total: 2-5 queries depending on item type
	"""
	# Parse item data (accept both JSON string and dict)
	item = json.loads(item) if isinstance(item, str) else item
	today = nowdate()
	item_code = item.get("item_code")
	batch_no_data = []
	serial_no_data = []

	# ===========================================================================
	# BATCH TRACKING: Get available batches with expiry filtering
	# ===========================================================================
	# For batch-tracked items (e.g., medicines, perishables), return only:
	# 1. Batches with qty > 0 (available stock)
	# 2. Non-expired batches (expiry_date > today or no expiry)
	# 3. Enabled batches (disabled = 0)
	#
	# Sorted by: Expiry date (FIFO - First to Expire, First Out)
	#
	# Use Case: POS cashier selects batch when adding item to cart
	# Example: Medicine "ABC" has 3 batches:
	#   - Batch A: 50 qty, expires in 2 days → INCLUDED (sell first!)
	#   - Batch B: 100 qty, expires in 30 days → INCLUDED
	#   - Batch C: 20 qty, expired yesterday → EXCLUDED
	if warehouse and item.get("has_batch_no"):
		# Get all batches with available quantity for this item in warehouse
		batch_list = get_batch_qty(warehouse=warehouse, item_code=item_code)
		if batch_list:
			for batch in batch_list:
				# Filter 1: Only batches with available stock
				if batch.qty > 0 and batch.batch_no:
					# Fetch batch metadata (expiry, manufacturing dates, disabled status)
					batch_doc = frappe.get_cached_doc("Batch", batch.batch_no)

					# Filter 2: Exclude expired batches
					# Filter 3: Exclude disabled batches
					is_not_expired = (
						str(batch_doc.expiry_date) > str(today)
						or batch_doc.expiry_date in ["", None]
					)
					is_enabled = batch_doc.disabled == 0

					if is_not_expired and is_enabled:
						batch_no_data.append({
							"batch_no": batch.batch_no,
							"batch_qty": batch.qty,
							"expiry_date": batch_doc.expiry_date,
							"manufacturing_date": batch_doc.manufacturing_date,
						})

	# ===========================================================================
	# SERIAL NUMBER TRACKING: Get available serial numbers
	# ===========================================================================
	# For serial-tracked items (e.g., laptops, phones), return only:
	# 1. Serial numbers with status = "Active" (not sold/scrapped)
	# 2. Serial numbers in the specified warehouse
	#
	# Serial numbers are unique identifiers for individual item units.
	# Each serial number can only be sold once.
	#
	# Use Case: POS cashier scans or selects serial number when selling
	# Example: Laptop "XYZ" has serial numbers:
	#   - SN001 (Active, Main Store) → INCLUDED
	#   - SN002 (Active, Main Store) → INCLUDED
	#   - SN003 (Delivered, Main Store) → EXCLUDED (already sold)
	#   - SN004 (Active, Branch Store) → EXCLUDED (different warehouse)
	if warehouse and item.get("has_serial_no"):
		serial_no_data = frappe.get_all(
			"Serial No",
			filters={
				"item_code": item_code,
				"status": "Active",  # Only available serial numbers
				"warehouse": warehouse,  # From specified warehouse only
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

	# Fetch all needed Item fields in a single query (performance optimization)
	item_data = frappe.db.get_value(
		"Item",
		item_code,
		["max_discount", "item_group", "brand", "stock_uom"],
		as_dict=True
	) or {}

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

	res["max_discount"] = item_data.get("max_discount")
	res["batch_no_data"] = batch_no_data
	res["serial_no_data"] = serial_no_data
	res["item_group"] = item_data.get("item_group")
	res["brand"] = item_data.get("brand")

	# Add UOMs data
	uoms = frappe.get_all(
		"UOM Conversion Detail",
		filters={"parent": item_code},
		fields=["uom", "conversion_factor"],
	)

	# Add stock UOM if not already in uoms list
	stock_uom = item_data.get("stock_uom")
	if stock_uom and not any(u.get("uom") == stock_uom for u in uoms):
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
		# Get both quantities in a single query (performance optimization)
		bin_data = frappe.db.get_value(
			"Bin",
			{"item_code": item_code, "warehouse": warehouse},
			["actual_qty", "reserved_qty"],
			as_dict=True
		) or {}

		stock_qty = flt(bin_data.get("actual_qty", 0))
		reserved_qty = flt(bin_data.get("reserved_qty", 0))

		return {
			"item_code": item_code,
			"warehouse": warehouse,
			"stock_qty": stock_qty,
			"reserved_qty": reserved_qty,
			"available_qty": stock_qty - reserved_qty,
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Item Stock Error")
		frappe.throw(_("Error fetching item stock: {0}").format(str(e)))


@frappe.whitelist()
def get_batch_serial_details(item_code, warehouse):
	"""Get batch/serial number details"""
	try:
		# Get both flags in a single query (performance optimization)
		item_flags = frappe.db.get_value(
			"Item", item_code,
			["has_batch_no", "has_serial_no"],
			as_dict=True
		) or {}

		has_batch_no = item_flags.get("has_batch_no")
		has_serial_no = item_flags.get("has_serial_no")

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

		# Get all variants of this template using Query Builder for Frappe 16 compatibility
		# Apply company filter: show variants for specific company + global variants (empty company)
		Item = DocType("Item")
		query = (
			frappe.qb.from_(Item)
			.select(
				Item.name.as_("item_code"),
				Item.item_name,
				Item.stock_uom,
				Item.image,
				Item.is_stock_item,
				Item.has_batch_no,
				Item.has_serial_no,
				Item.item_group,
				Item.brand,
				Item.custom_company,
				Item.variant_of,
			)
			.where(Item.variant_of == template_item)
			.where(Item.disabled == 0)
			.where(Item.is_sales_item == 1)
		)

		# Add company filter to show items for specific company + global items
		if pos_profile_doc.company:
			query = query.where(
				fn.Coalesce(Item.custom_company, "").isin([pos_profile_doc.company, ""])
			)

		variants = query.run(as_dict=True)

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
		"i.disabled = 0",
		"i.is_sales_item = 1",
		"IFNULL(i.variant_of, '') = ''",
	]
	params = []

	if pos_profile_doc.company:
		conditions.append("(IFNULL(custom_company, '') IN (%s, ''))")
		params.append(pos_profile_doc.company)

	if item_group:
		conditions.append("item_group = %s")
		params.append(item_group)

	return conditions, params


def _calculate_bundle_availability_bulk(bundle_codes, warehouse):
	"""
	Calculate Product Bundle availability in bulk with component-based calculation.

	This function determines how many complete bundles can be assembled based on
	available component stock. It uses available_qty (actual - reserved) to prevent
	overselling and supports group warehouses for hierarchical stock tracking.

	Product Bundle Availability Logic:
	=====================================
	A bundle's availability is limited by its MOST CONSTRAINED component.

	Example:
		Bundle: "Laptop Combo"
		Components:
			- Laptop (need 1) → available: 50 units → can make 50 bundles
			- Mouse (need 1) → available: 30 units → can make 30 bundles ← LIMITING
			- Keyboard (need 1) → available: 100 units → can make 100 bundles

		Result: Bundle availability = 30 (limited by Mouse stock)

	Stock Calculation:
	==================
	Uses AVAILABLE quantity (actual_qty - reserved_qty) instead of actual_qty
	to prevent overselling when items are reserved in other pending orders.

	Performance Optimization:
	=========================
	- Single bulk query for all bundle components
	- Single bulk query for all component stock levels
	- Handles multiple bundles simultaneously
	- Supports group warehouses (auto-expands to child warehouses)

	Group Warehouse Support:
	========================
	If warehouse is a group warehouse, automatically includes stock from all
	child warehouses in the calculation. This provides accurate availability
	across multiple storage locations.

	Args:
		bundle_codes (list): List of bundle item codes to check
		warehouse (str): Warehouse name (supports group warehouses)

	Returns:
		dict: Mapping of bundle_code -> available_quantity
			  Example: {"BUNDLE-001": 30, "BUNDLE-002": 15}
			  Returns empty dict if no bundles or warehouse not provided

	Example Usage:
		>>> bundles = ["LAPTOP-COMBO", "DESKTOP-BUNDLE"]
		>>> availability = _calculate_bundle_availability_bulk(bundles, "Stores - WH")
		>>> print(availability)
		{"LAPTOP-COMBO": 30, "DESKTOP-BUNDLE": 15}

	Database Queries:
		1. Fetch all bundle components (1 query for all bundles)
		2. Fetch stock for all components (1 query for all items)
		Total: 2 queries regardless of number of bundles

	Edge Cases:
		- No bundles: Returns {}
		- No warehouse: Returns {}
		- Component with 0 stock: Bundle availability = 0
		- Component not in stock table: Treated as 0 availability
		- Group warehouse with no children: Falls back to warehouse itself
	"""
	# ===========================================================================
	# GUARD CLAUSE: Validate inputs
	# ===========================================================================
	if not bundle_codes or not warehouse:
		return {}

	# ===========================================================================
	# STEP 1: Fetch Bundle Component Definitions
	# ===========================================================================
	# Query all bundle definitions and their components in a single query.
	# This is more efficient than querying each bundle separately.
	#
	# Example Result:
	# [
	#   {"bundle_code": "LAPTOP-COMBO", "component_code": "LAPTOP", "required_qty": 1},
	#   {"bundle_code": "LAPTOP-COMBO", "component_code": "MOUSE", "required_qty": 1},
	#   {"bundle_code": "LAPTOP-COMBO", "component_code": "KEYBOARD", "required_qty": 1}
	# ]
	pb = DocType("Product Bundle")
	pbi = DocType("Product Bundle Item")
	
	bundle_components = (
		frappe.qb.from_(pb)
		.inner_join(pbi).on(pbi.parent == pb.name)
		.select(
			pb.new_item_code.as_("bundle_code"),
			pbi.item_code.as_("component_code"),
			pbi.qty.as_("required_qty")
		)
		.where(pb.new_item_code.isin(bundle_codes))
		.run(as_dict=True)
	)

	if not bundle_components:
		# No bundle definitions found - items are not configured as bundles
		return {}

	# ===========================================================================
	# STEP 2: Extract Unique Component Codes
	# ===========================================================================
	# Get all unique component item codes needed across all bundles.
	# This allows us to fetch stock for all components in a single query.
	#
	# Example: {"LAPTOP", "MOUSE", "KEYBOARD", "MONITOR", "CABLE"}
	component_codes = list(set(c["component_code"] for c in bundle_components))

	# ===========================================================================
	# STEP 3: Resolve Warehouse Hierarchy (Group Warehouse Support)
	# ===========================================================================
	# If the warehouse is a group warehouse, expand to include all child warehouses.
	# This provides accurate stock availability across multiple storage locations.
	#
	# Example:
	#   Input: "Main Store" (group warehouse)
	#   Output: ["Main Store - A", "Main Store - B", "Main Store - C"]
	warehouses = [warehouse]
	if frappe.db.get_value("Warehouse", warehouse, "is_group"):
		child_warehouses = frappe.db.get_descendants("Warehouse", warehouse)
		# Fallback to original warehouse if no children found
		warehouses = child_warehouses or [warehouse]

	# ===========================================================================
	# STEP 4: Fetch Stock Availability for All Components (Bulk Query)
	# ===========================================================================
	# Query stock for all component items across all warehouses in ONE query.
	# Uses available_qty (actual - reserved) to prevent overselling.
	#
	# Performance: Single query handles all components regardless of count
	# Formula: available_qty = actual_qty - reserved_qty
	#
	# Example Result:
	# [
	#   {"item_code": "LAPTOP", "available_qty": 50.0},
	#   {"item_code": "MOUSE", "available_qty": 30.0},
	#   {"item_code": "KEYBOARD", "available_qty": 100.0}
	# ]
	bin = DocType("Bin")
	
	component_stock = (
		frappe.qb.from_(bin)
		.select(
			bin.item_code,
			fn.Coalesce(fn.Sum(bin.actual_qty - bin.reserved_qty), 0).as_("available_qty")
		)
		.where(bin.item_code.isin(component_codes))
		.where(bin.warehouse.isin(warehouses))
		.groupby(bin.item_code)
		.run(as_dict=True)
	)

	# Build fast lookup map: item_code -> available_qty
	# Components not in map are treated as having 0 stock
	component_stock_map = {row["item_code"]: flt(row["available_qty"]) for row in component_stock}

	# ===========================================================================
	# STEP 5: Calculate Bundle Availability (Limited by Most Constrained Component)
	# ===========================================================================
	# For each bundle, determine how many complete bundles can be made based on
	# component availability. The bundle quantity is limited by whichever
	# component can make the FEWEST bundles.
	#
	# Formula: possible_bundles = floor(available_qty / required_qty)
	# Final: bundle_qty = min(possible_bundles across all components)
	#
	# Example:
	#   LAPTOP-COMBO components:
	#     - LAPTOP (need 1): 50 available → 50 possible bundles
	#     - MOUSE (need 1): 30 available → 30 possible bundles ← LIMITING FACTOR
	#     - KEYBOARD (need 1): 100 available → 100 possible bundles
	#   Result: LAPTOP-COMBO availability = 30 (limited by MOUSE)
	bundle_availability = {}
	for comp in bundle_components:
		bundle_code = comp["bundle_code"]
		available = component_stock_map.get(comp["component_code"], 0)
		required = flt(comp["required_qty"])

		if required > 0:
			# Calculate how many bundles this component can supply
			possible = int(available / required)

			# Update bundle availability with minimum across all components
			if bundle_code not in bundle_availability:
				# First component for this bundle
				bundle_availability[bundle_code] = possible
			else:
				# Subsequent components - take minimum (most constrained)
				bundle_availability[bundle_code] = min(bundle_availability[bundle_code], possible)

	return bundle_availability


def _get_bundle_warehouse_availability_bulk(bundle_codes, warehouses):
	"""
	Calculate Product Bundle availability across multiple warehouses efficiently.
	
	Args:
		bundle_codes (list): List of bundle item codes
		warehouses (list): List of warehouse dicts with 'name' key
		
	Returns:
		dict: Nested mapping of bundle_code -> warehouse_name -> available_qty
			  Example: {
				  "BUNDLE-001": {"Warehouse A": 30, "Warehouse B": 15},
				  "BUNDLE-002": {"Warehouse A": 10}
			  }
	"""
	if not bundle_codes or not warehouses:
		return {}
	
	warehouse_names = [w["name"] if isinstance(w, dict) else w for w in warehouses]
	
	# ===========================================================================
	# Fetch Bundle Component Definitions (once for all bundles)
	# ===========================================================================
	pb = DocType("Product Bundle")
	pbi = DocType("Product Bundle Item")
	
	bundle_components = (
		frappe.qb.from_(pb)
		.inner_join(pbi).on(pbi.parent == pb.name)
		.select(
			pb.new_item_code.as_("bundle_code"),
			pbi.item_code.as_("component_code"),
			pbi.qty.as_("required_qty")
		)
		.where(pb.new_item_code.isin(bundle_codes))
		.run(as_dict=True)
	)
	
	if not bundle_components:
		return {}

	component_codes = list(set(c["component_code"] for c in bundle_components))
	warehouse_resolution_map = {}
	all_resolved_warehouses = set()
	
	for wh_name in warehouse_names:
		resolved = [wh_name]
		if frappe.db.get_value("Warehouse", wh_name, "is_group"):
			children = frappe.db.get_descendants("Warehouse", wh_name)
			if children:
				resolved = children
		warehouse_resolution_map[wh_name] = resolved
		all_resolved_warehouses.update(resolved)
	
	# ===========================================================================
	# Fetch Component Stock Across All Warehouses (single bulk query)
	# ===========================================================================
	bin = DocType("Bin")
	
	component_stock_data = (
		frappe.qb.from_(bin)
		.select(
			bin.item_code,
			bin.warehouse,
			fn.Coalesce(fn.Sum(bin.actual_qty - bin.reserved_qty), 0).as_("available_qty")
		)
		.where(bin.item_code.isin(component_codes))
		.where(bin.warehouse.isin(list(all_resolved_warehouses)))
		.groupby(bin.item_code, bin.warehouse)
		.run(as_dict=True)
	)
	
	# Build lookup: (item_code, warehouse) -> available_qty
	# For group warehouses, sum stock from all child warehouses
	component_stock_map = defaultdict(lambda: defaultdict(float))
	for row in component_stock_data:
		component_stock_map[row["item_code"]][row["warehouse"]] = flt(row["available_qty"])
	
	# ===========================================================================
	# Calculate Bundle Availability Per Warehouse
	# ===========================================================================
	# For each bundle and each warehouse, calculate availability
	# Availability = min(floor(component_available / component_required)) across all components
	result = defaultdict(dict)
	
	# Group components by bundle (build once, reuse for all warehouses)
	bundles_map = defaultdict(list)
	for comp in bundle_components:
		bundles_map[comp["bundle_code"]].append(comp)
	
	# Calculate availability for each bundle in each warehouse
	for wh_name in warehouse_names:
		resolved_whs = warehouse_resolution_map[wh_name]
		
		for bundle_code, components in bundles_map.items():
			min_possible = None
			
			for comp in components:
				component_code = comp["component_code"]
				required_qty = flt(comp["required_qty"])
				
				if required_qty <= 0:
					continue
				
				# Sum stock across all resolved warehouses (for group warehouse support)
				total_available = sum(
					component_stock_map[component_code].get(wh, 0)
					for wh in resolved_whs
				)
				
				# Calculate how many bundles this component can supply
				possible = int(total_available / required_qty) if required_qty > 0 else 0
				
				# Track minimum (most constrained component)
				if min_possible is None:
					min_possible = possible
				else:
					min_possible = min(min_possible, possible)
			
			# Only include if bundle is available (min_possible > 0)
			if min_possible is not None and min_possible > 0:
				result[bundle_code][wh_name] = min_possible
	
	return dict(result)


@frappe.whitelist()
def get_items(pos_profile, search_term=None, item_group=None, start=0, limit=20):
	"""Get items for POS with stock, price, and tax details"""
	try:
		pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)

		# Try to resolve weighted/priced barcodes if barcode_resolver is available
		resolved_barcode_data = None
		effective_search_term = search_term
		if search_term and len(search_term.strip().split()) == 1:
			from pos_next.services.barcode import resolve_barcode
			resolved_barcode_data = resolve_barcode(search_term.strip(), pos_profile)
			if resolved_barcode_data and resolved_barcode_data.get("item_barcode"):
				# Use the extracted item barcode for searching
				effective_search_term = resolved_barcode_data["item_barcode"]

		# IMPORTANT: Filtering logic explained:
		# - Template items (has_variants=1) are shown → users select variants via dialog
		# - Regular items (has_variants=0, variant_of is null) are shown → direct add to cart
		# - Variant items (has_variants=0, variant_of is not null) are HIDDEN from main list

		# Add company filter - show items for specific company + global items (empty company)
		# Global items (custom_company is empty) are available to all companies

		# Build base conditions
		conditions, params = _build_item_base_conditions(pos_profile_doc, item_group)

		# Build column list with table alias
		item_columns = ",\n\t".join([f"i.{col}" for col in ITEM_RESULT_FIELDS])
		# For GROUP BY, extract just the column name (before " as " if present)
		group_by_columns = ", ".join([
			f"i.{col.split(' as ')[0]}" for col in ITEM_RESULT_FIELDS
		])

		# Add search conditions if search term provided
		if effective_search_term and effective_search_term.strip():
			# Split search term into words for fuzzy matching
			search_words = [word.strip() for word in effective_search_term.split() if word.strip()]

			# Word-order independent: all words must appear somewhere in item fields
			search_text = "CONCAT(COALESCE(i.name, ''), ' ', COALESCE(i.item_name, ''), ' ', COALESCE(i.description, ''))"
			word_conditions = " AND ".join([f"{search_text} LIKE %s"] * len(search_words))

			# Also match if barcode contains the search term
			barcode_condition = "ib.barcode LIKE %s"

			# Combine: match item fields OR match barcode
			conditions.append(f"(({word_conditions}) OR {barcode_condition})")
			params.extend([f"%{word}%" for word in search_words])
			params.append(f"%{effective_search_term}%")  # For barcode matching

			# Relevance scoring with case-insensitive comparison
			# Exact barcode match gets highest priority, use MAX() for grouping
			prefix_pattern = f"{effective_search_term}%"
			relevance = f"""
				MAX(CASE
					WHEN ib.barcode = %s THEN 1500
					WHEN ib.barcode LIKE %s THEN 1200
					WHEN LOWER(i.item_name) = LOWER(%s) THEN 1000
					WHEN LOWER(i.name) = LOWER(%s) THEN 900
					WHEN LOWER(i.item_name) LIKE LOWER(%s) THEN 500
					WHEN LOWER(i.name) LIKE LOWER(%s) THEN 400
					ELSE 100
				END)
			"""
			score_params = [effective_search_term, prefix_pattern, effective_search_term, effective_search_term, prefix_pattern, prefix_pattern]
			order_by = f"{relevance} DESC, i.item_name ASC"
		else:
			# No search term - simple ordering
			score_params = []
			order_by = "i.item_name ASC"

		where_clause = " AND ".join(conditions)

		query = f"""
			SELECT {item_columns},
				GROUP_CONCAT(DISTINCT ib.barcode) as barcode,
				GROUP_CONCAT(DISTINCT ib.uom) as barcode_uoms
			FROM `tabItem` i
			LEFT JOIN `tabItem Barcode` ib ON ib.parent = i.name
			WHERE {where_clause}
			GROUP BY {group_by_columns}
			ORDER BY {order_by}
			LIMIT %s OFFSET %s
		"""

		params.extend(score_params)
		params.extend([limit, start])
		items = frappe.db.sql(query, tuple(params), as_dict=1)

		# Prepare maps for enrichment
		item_codes = [item["item_code"] for item in items]
		conversion_map = defaultdict(dict)  # parent -> {uom: factor}
		uom_map = {}  # parent -> [ {uom, conversion_factor}, ... ]
		uom_prices_map = {}  # item_code -> {uom: price_list_rate}

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

		# ===================================================================
		# PRODUCT BUNDLE AVAILABILITY: Calculate bundle stock (bulk optimized)
		# ===================================================================
		# Product Bundles are "virtual" items assembled from component items.
		# Unlike regular stock items, bundles don't have direct stock entries.
		# Instead, availability is calculated from component stock levels.
		#
		# Example:
		#   Bundle: "Office Starter Kit"
		#   Components:
		#     - Desk (need 1, have 10) → can make 10 bundles
		#     - Chair (need 2, have 15) → can make 7 bundles ← LIMITING
		#     - Lamp (need 1, have 20) → can make 20 bundles
		#   Result: Bundle availability = 7 (limited by chairs)
		#
		# Performance: Single bulk calculation for ALL bundles (not per-item)
		# This is done BEFORE the item enrichment loop for efficiency.
		bundle_availability_map = {}
		if item_codes and pos_profile_doc.warehouse:
			# Bulk calculate availability for all items (bundles auto-detected)
			bundle_availability_map = _calculate_bundle_availability_bulk(
				item_codes,
				pos_profile_doc.warehouse
			)
		elif item_codes and not pos_profile_doc.warehouse:
			# Warning: Bundles require warehouse for component stock lookup
			# Without warehouse, bundles will show as unavailable (qty = 0)
			has_bundles = frappe.db.exists("Product Bundle", {"new_item_code": ["in", item_codes]})
			if has_bundles:
				frappe.log_error(
					"POS Profile missing warehouse - Product Bundles will show as unavailable",
					"Bundle Availability Warning"
				)

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

			# ===================================================================
			# STOCK QUANTITY ASSIGNMENT: Stock Items vs Product Bundles
			# ===================================================================
			# Stock items: Use actual_qty from Bin table (direct stock tracking)
			# Product Bundles: Use calculated availability from component stock
			#
			# Decision Logic:
			#   IF item.is_stock_item == 1:
			#     actual_qty = stock from Bin table (or 0 if not in stock)
			#   ELSE:
			#     actual_qty = bundle availability (or 0 if not a bundle)
			#
			# Example 1 - Stock Item (Laptop):
			#   is_stock_item = 1
			#   actual_qty = 50 (from Bin table)
			#
			# Example 2 - Product Bundle (Office Kit):
			#   is_stock_item = 0 (bundles are not stock items)
			#   actual_qty = 7 (calculated from components)
			#
			# Example 3 - Service Item (Consulting):
			#   is_stock_item = 0
			#   actual_qty = 0 (not a bundle, no stock tracking)
			item["actual_qty"] = (
				stock_map.get(item["item_code"], 0)
				if item.get("is_stock_item")
				else bundle_availability_map.get(item["item_code"], 0)
			)

			# ===================================================================
			# BUNDLE MARKER: Flag items that are Product Bundles
			# ===================================================================
			# Add is_bundle=True flag for frontend to identify bundle items.
			# This allows UI to show bundle-specific indicators and handle
			# bundle logic differently (e.g., show component details on click).
			#
			# Bundle Detection: If item_code exists in bundle_availability_map,
			# it means a Product Bundle definition exists for this item.
			if item["item_code"] in bundle_availability_map:
				item["is_bundle"] = True

			# Add warehouse to item (needed for stock validation)
			item["warehouse"] = pos_profile_doc.warehouse

			# Barcode
			# item["barcode"] = barcode_map.get(item["item_code"], "")

			# Item UOMs (exclude stock UOM to avoid duplicates)
			all_uoms = uom_map.get(item["item_code"], []) or []
			item["item_uoms"] = [u for u in all_uoms if u.get("uom") != stock_uom]

			# UOM-specific prices map for frontend selector
			item["uom_prices"] = uom_prices_map.get(item["item_code"], {})

		# Apply resolved barcode data (weighted/priced) to the first matching item
		if resolved_barcode_data and items:
			from pos_next.services.barcode import compute_resolved_item_data
			resolved_item_data = compute_resolved_item_data(
				resolved_barcode_data,
				item=items[0],
			)
			if resolved_item_data:
				items[0].update(resolved_item_data)

		return items
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Items Error")
		frappe.throw(_("Error fetching items: {0}").format(str(e)))


@frappe.whitelist()
def get_item_details(item_code, pos_profile, customer=None, qty=1, uom=None):  # noqa: ARG001 - customer reserved for future use
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
		item_stock_map = {row["item_code"]: row for row in stock_rows}

		# Get bundle availability for non-stock items (bulk optimized)
		bundle_availability_map = _calculate_bundle_availability_bulk(normalized_codes, warehouse)

		# Return stock for all requested items
		result = []
		for item_code in normalized_codes:
			# Check if it's a bundle
			if item_code in bundle_availability_map:
				# Bundle item - use calculated availability
				actual_qty = flt(bundle_availability_map[item_code])
				reserved_qty = 0.0
			else:
				# Regular item - use Bin data
				row = item_stock_map.get(item_code)
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


# =============================================================================
# WAREHOUSE AVAILABILITY HELPERS
# =============================================================================

def _get_warehouse_display_name(warehouse_id, warehouse_map, fallback_company=None):
	"""
	Get display name for a warehouse with fallback logic.

	Fallback order:
	1. warehouse_name from cached map
	2. warehouse.name (ID) from cached map
	3. Fetch from DB if not in map (handles disabled/group warehouses)
	4. Use warehouse_id as last resort
	"""
	warehouse = warehouse_map.get(warehouse_id)
	if warehouse:
		return warehouse.warehouse_name or warehouse.name, warehouse.company

	# Fallback: fetch from DB if not in active warehouse map
	wh_details = frappe.db.get_value("Warehouse", warehouse_id, ["warehouse_name", "company"], as_dict=True)
	if wh_details:
		return wh_details.warehouse_name or warehouse_id, wh_details.company
	return warehouse_id, fallback_company or ""


def _build_stock_entry(warehouse_id, actual_qty, reserved_qty, warehouse_map, item_code=None, fallback_company=None):
	"""
	Build a standardized stock entry dict with warehouse details.

	Returns:
		dict with warehouse, warehouse_name, actual_qty, reserved_qty, available_qty, company
		and optionally item_code if provided
	"""
	wh_name, wh_company = _get_warehouse_display_name(warehouse_id, warehouse_map, fallback_company)
	entry = {
		"warehouse": warehouse_id,
		"warehouse_name": wh_name,
		"actual_qty": flt(actual_qty),
		"reserved_qty": flt(reserved_qty),
		"available_qty": flt(actual_qty) - flt(reserved_qty),
		"company": wh_company
	}
	if item_code:
		entry["item_code"] = item_code
	return entry


def _parse_item_codes_param(item_codes):
	"""
	Parse item_codes parameter from JSON string or list.
	Handles: JSON string, list, tuple, or single value.
	"""
	if isinstance(item_codes, str):
		try:
			item_codes = json.loads(item_codes)
		except (json.JSONDecodeError, ValueError):
			return [item_codes]
	return list(item_codes) if isinstance(item_codes, (list, tuple)) else [item_codes]


# =============================================================================
# WAREHOUSE AVAILABILITY API
# =============================================================================

@frappe.whitelist()
def get_item_warehouse_availability(item_code=None, item_codes=None, company=None):
	"""
	Get stock availability for item(s) across all warehouses.
	Useful for showing cashiers where out-of-stock items are available.

	Handles:
	- Regular items: Shows stock in all warehouses
	- Item variants: Shows stock for the specific variant
	- Template items (has_variants): Shows combined stock of all variants
	- Product Bundles: Calculates availability based on component stock
	- Multiple items: Shows stock for each item separately

	Args:
		item_code: Single item code (backward compatible)
		item_codes: List of item codes (JSON string or list) - if provided, item_code is ignored
		company: Optional company filter

	Returns:
		List of warehouse stock entries:
		[{
			"item_code": str,      # Only present if item_codes provided
			"warehouse": str,
			"warehouse_name": str,
			"actual_qty": float,
			"reserved_qty": float,
			"available_qty": float,
			"company": str
		}]
	"""
	try:
		# ---------------------------------------------------------------------
		# STEP 1: Determine which items to check
		# ---------------------------------------------------------------------
		if item_codes:
			items_to_check = _parse_item_codes_param(item_codes)
			include_item_code = True
		elif item_code:
			item_doc = frappe.get_cached_doc("Item", item_code)
			items_to_check = [item_code]
			# If template item, include all its variants
			if item_doc.has_variants:
				items_to_check += frappe.get_all(
					"Item", filters={"variant_of": item_code, "disabled": 0}, pluck="name"
				)
			include_item_code = False
		else:
			frappe.throw(_("Either item_code or item_codes must be provided"))

		# ---------------------------------------------------------------------
		# STEP 2: Get active warehouses (non-disabled, non-group)
		# ---------------------------------------------------------------------
		wh_filters = {"disabled": 0, "is_group": 0}
		if company:
			wh_filters["company"] = company

		warehouses = frappe.get_list(
			"Warehouse", filters=wh_filters,
			fields=["name", "warehouse_name", "company"],
			order_by="warehouse_name"
		)
		if not warehouses:
			return []

		warehouse_map = {w.name: w for w in warehouses}
		warehouse_names = list(warehouse_map.keys())

		# ---------------------------------------------------------------------
		# STEP 3: Separate Product Bundles from regular stock items
		# ---------------------------------------------------------------------
		bundle_set = set(frappe.get_all(
			"Product Bundle",
			filters={"new_item_code": ["in", items_to_check]},
			pluck="new_item_code"
		) or [])
		regular_items = [i for i in items_to_check if i not in bundle_set]

		result = []

		# ---------------------------------------------------------------------
		# STEP 4: Query stock for regular items from Bin table
		# ---------------------------------------------------------------------
		if regular_items:
			bin_tbl = DocType("Bin")
			query = (
				frappe.qb.from_(bin_tbl)
				.select(
					bin_tbl.warehouse,
					fn.Sum(bin_tbl.actual_qty).as_("actual_qty"),
					fn.Sum(bin_tbl.reserved_qty).as_("reserved_qty")
				)
				.where(bin_tbl.item_code.isin(regular_items))
				.where(bin_tbl.warehouse.isin(warehouse_names))
				.having(fn.Sum(bin_tbl.actual_qty) > 0)
			)

			# Group by item_code too when multiple items requested
			if include_item_code:
				query = query.select(bin_tbl.item_code).groupby(bin_tbl.item_code, bin_tbl.warehouse)
			else:
				query = query.groupby(bin_tbl.warehouse)

			for stock in query.run(as_dict=True):
				result.append(_build_stock_entry(
					stock.warehouse, stock.actual_qty, stock.reserved_qty,
					warehouse_map, stock.get("item_code") if include_item_code else None, company
				))

		# ---------------------------------------------------------------------
		# STEP 5: Calculate availability for Product Bundles
		# Bundle availability = min(component_qty / required_qty) per warehouse
		# ---------------------------------------------------------------------
		if bundle_set:
			bundle_availability = _get_bundle_warehouse_availability_bulk(
				list(bundle_set), [{"name": w} for w in warehouse_names]
			)
			for bundle_code, wh_qtys in bundle_availability.items():
				for wh_name, qty in wh_qtys.items():
					if qty > 0:
						result.append(_build_stock_entry(
							wh_name, qty, 0, warehouse_map,
							bundle_code if include_item_code else None, company
						))

		return result

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Warehouse Availability Error")
		frappe.throw(_("Error fetching warehouse availability: {0}").format(str(e)))


@frappe.whitelist()
def get_product_bundle_availability(item_code, warehouse):
	"""
	Get Product Bundle availability with detailed component information.
	Uses available_qty (actual - reserved) to prevent overselling.

	Returns:
		{
			"available_qty": int,
			"components": [
				{
					"item_code": str,
					"item_name": str,
					"required_qty": float,
					"available_qty": float,
					"possible_bundles": int,
					"uom": str,
					"is_limiting": bool  # True if this component limits bundle qty
				}
			]
		}
	"""
	try:
		# Use bulk calculation for single bundle
		bundle_availability = _calculate_bundle_availability_bulk([item_code], warehouse)
		available_qty = bundle_availability.get(item_code, 0)

		# Get detailed component information with item names (single query with JOIN)
		components = frappe.db.sql("""
			SELECT
				pbi.item_code,
				i.item_name,
				pbi.qty as required_qty,
				pbi.uom
			FROM `tabProduct Bundle Item` pbi
			INNER JOIN `tabItem` i ON i.name = pbi.item_code
			WHERE pbi.parent = %(bundle)s
			ORDER BY pbi.idx
		""", {"bundle": item_code}, as_dict=1)

		if not components:
			return {"available_qty": 0, "components": []}

		# Get warehouses (support group warehouses)
		warehouses = [warehouse]
		if frappe.db.get_value("Warehouse", warehouse, "is_group"):
			warehouses = frappe.db.get_descendants("Warehouse", warehouse) or [warehouse]

		# Get component stock (use available = actual - reserved)
		component_codes = [c["item_code"] for c in components]
		stock_data = frappe.db.sql("""
			SELECT
				item_code,
				COALESCE(SUM(actual_qty - reserved_qty), 0) as available_qty
			FROM `tabBin`
			WHERE item_code IN %(items)s AND warehouse IN %(warehouses)s
			GROUP BY item_code
		""", {"items": component_codes, "warehouses": warehouses}, as_dict=1)

		component_stock_map = {row["item_code"]: flt(row["available_qty"]) for row in stock_data}

		# Build component details with limiting indicator
		component_details = []
		for comp in components:
			available = component_stock_map.get(comp["item_code"], 0)
			required = flt(comp["required_qty"])
			possible = int(available / required) if required > 0 else 0

			component_details.append({
				"item_code": comp["item_code"],
				"item_name": comp["item_name"],
				"required_qty": required,
				"available_qty": available,
				"possible_bundles": possible,
				"uom": comp["uom"],
				"is_limiting": (possible == available_qty)  # Mark limiting component
			})

		return {
			"available_qty": available_qty,
			"components": component_details
		}

	except Exception as e:
		frappe.log_error(
			frappe.get_traceback(),
			f"Bundle Availability Error: {item_code} in {warehouse}"
		)
		frappe.throw(_("Error fetching bundle availability for {0}: {1}").format(item_code, str(e)))


@frappe.whitelist()
def get_batch_serial_data_for_items(item_codes, warehouse):
	"""
	Get batch and serial number data for multiple items (for offline caching).

	This endpoint is optimized for bulk fetching to enable offline batch/serial selection.
	Similar to how variants are cached for offline use.

	Args:
		item_codes (list|str): List of item codes or JSON string
		warehouse (str): Warehouse to fetch stock from

	Returns:
		dict: Mapping of item_code to batch/serial data
			{
				"ITEM-001": {
					"batch_no_data": [...],
					"serial_no_data": [...]
				},
				...
			}
	"""
	try:
		if isinstance(item_codes, str):
			item_codes = json.loads(item_codes)

		if not item_codes or not warehouse:
			return {}

		today = nowdate()
		result = {}

		# Get item details to check which items have batch/serial tracking
		Item = DocType("Item")
		items = (
			frappe.qb.from_(Item)
			.select(
				Item.name.as_("item_code"),
				Item.has_batch_no,
				Item.has_serial_no,
			)
			.where(Item.name.isin(item_codes))
			.run(as_dict=True)
		)

		items_map = {item["item_code"]: item for item in items}

		# Batch items - fetch all batches in bulk
		batch_items = [code for code in item_codes if items_map.get(code, {}).get("has_batch_no")]
		serial_items = [code for code in item_codes if items_map.get(code, {}).get("has_serial_no")]

		# Initialize result for all items
		for item_code in item_codes:
			result[item_code] = {
				"batch_no_data": [],
				"serial_no_data": [],
			}

		# Fetch batch data for batch-tracked items
		if batch_items:
			for item_code in batch_items:
				batch_list = get_batch_qty(warehouse=warehouse, item_code=item_code)
				if batch_list:
					for batch in batch_list:
						if batch.qty > 0 and batch.batch_no:
							batch_doc = frappe.get_cached_doc("Batch", batch.batch_no)
							is_not_expired = (
								str(batch_doc.expiry_date) > str(today)
								or batch_doc.expiry_date in ["", None]
							)
							is_enabled = batch_doc.disabled == 0

							if is_not_expired and is_enabled:
								result[item_code]["batch_no_data"].append({
									"batch_no": batch.batch_no,
									"batch_qty": batch.qty,
									"expiry_date": str(batch_doc.expiry_date) if batch_doc.expiry_date else None,
									"manufacturing_date": str(batch_doc.manufacturing_date) if batch_doc.manufacturing_date else None,
								})

		# Fetch serial data for serial-tracked items in bulk
		if serial_items:
			serials = frappe.get_all(
				"Serial No",
				filters={
					"item_code": ["in", serial_items],
					"status": "Active",
					"warehouse": warehouse,
				},
				fields=["name as serial_no", "item_code", "warehouse"],
			)

			# Group by item_code
			for serial in serials:
				result[serial["item_code"]]["serial_no_data"].append({
					"serial_no": serial["serial_no"],
					"warehouse": serial["warehouse"],
				})

		return result

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Batch/Serial Data for Items Error")
		return {}
