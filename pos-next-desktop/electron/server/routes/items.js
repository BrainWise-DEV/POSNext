const { getDatabase } = require("../db/connection")
const { FrappeError } = require("../frappe-compat")

/**
 * Items API - replaces pos_next.api.items
 * Full-text search, barcode lookup, stock queries against local SQLite.
 */

async function getItems(params) {
	const db = getDatabase()
	const {
		pos_profile,
		item_group,
		search_term,
		start = 0,
		page_length = 20,
		price_list,
		warehouse,
	} = params

	let query = `
		SELECT i.item_code, i.item_name, i.description, i.stock_uom, i.image,
			   i.is_stock_item, i.has_batch_no, i.has_serial_no, i.item_group,
			   i.brand, i.has_variants, i.variant_of, i.custom_company, i.disabled
		FROM items i
		WHERE i.disabled = 0 AND i.is_sales_item = 1
	`
	const queryParams = []

	// Filter by item group (with descendants using lft/rgt)
	if (item_group && item_group !== "All Item Groups") {
		const group = db.prepare("SELECT lft, rgt FROM item_groups WHERE name = ?").get(item_group)
		if (group) {
			query += ` AND i.item_group IN (
				SELECT name FROM item_groups WHERE lft >= ? AND rgt <= ?
			)`
			queryParams.push(group.lft, group.rgt)
		}
	}

	// Search by term (FTS5)
	if (search_term) {
		const ftsQuery = search_term.replace(/[^\w\s]/g, "") + "*"
		query += ` AND i.item_code IN (
			SELECT item_code FROM items_fts WHERE items_fts MATCH ?
		)`
		queryParams.push(ftsQuery)
	}

	// Exclude template items (show variants instead)
	query += " AND i.has_variants = 0"

	query += " ORDER BY i.item_name ASC LIMIT ? OFFSET ?"
	queryParams.push(page_length, start)

	const items = db.prepare(query).all(...queryParams)

	// Attach prices and stock
	const priceList = price_list || _getDefaultPriceList(db, pos_profile)
	for (const item of items) {
		// Get price
		if (priceList) {
			const price = db.prepare(
				"SELECT price_list_rate FROM item_prices WHERE price_list = ? AND item_code = ?"
			).get(priceList, item.item_code)
			item.price_list_rate = price?.price_list_rate || 0
			item.rate = price?.price_list_rate || 0
		}

		// Get stock
		if (warehouse) {
			const stock = db.prepare(
				"SELECT actual_qty FROM stock WHERE item_code = ? AND warehouse = ?"
			).get(item.item_code, warehouse)
			item.actual_qty = stock?.actual_qty || 0
		}

		// Get barcodes
		item.barcodes = db.prepare(
			"SELECT barcode FROM item_barcodes WHERE item_code = ?"
		).all(item.item_code).map(b => b.barcode)
	}

	return items
}

async function getItemsBulk(params) {
	const db = getDatabase()
	const { item_groups = [], pos_profile, price_list, warehouse, start = 0, page_length = 500 } = params

	const groups = typeof item_groups === "string" ? JSON.parse(item_groups) : item_groups

	if (!groups.length) return []

	// Get all descendant groups
	const placeholders = groups.map(() => "?").join(",")
	const descendantGroups = db.prepare(`
		SELECT DISTINCT ig2.name
		FROM item_groups ig1
		JOIN item_groups ig2 ON ig2.lft >= ig1.lft AND ig2.rgt <= ig1.rgt
		WHERE ig1.name IN (${placeholders})
	`).all(...groups).map(r => r.name)

	const groupPlaceholders = descendantGroups.map(() => "?").join(",")
	const items = db.prepare(`
		SELECT item_code, item_name, description, stock_uom, image,
			   is_stock_item, has_batch_no, has_serial_no, item_group,
			   brand, has_variants, variant_of, custom_company, disabled
		FROM items
		WHERE disabled = 0 AND is_sales_item = 1 AND has_variants = 0
		AND item_group IN (${groupPlaceholders})
		ORDER BY item_name ASC
		LIMIT ? OFFSET ?
	`).all(...descendantGroups, page_length, start)

	return items
}

async function getItemsCount(params) {
	const db = getDatabase()
	const { item_group, search_term } = params

	let query = "SELECT COUNT(*) as count FROM items WHERE disabled = 0 AND is_sales_item = 1 AND has_variants = 0"
	const queryParams = []

	if (item_group && item_group !== "All Item Groups") {
		const group = db.prepare("SELECT lft, rgt FROM item_groups WHERE name = ?").get(item_group)
		if (group) {
			query += " AND item_group IN (SELECT name FROM item_groups WHERE lft >= ? AND rgt <= ?)"
			queryParams.push(group.lft, group.rgt)
		}
	}

	if (search_term) {
		const ftsQuery = search_term.replace(/[^\w\s]/g, "") + "*"
		query += " AND item_code IN (SELECT item_code FROM items_fts WHERE items_fts MATCH ?)"
		queryParams.push(ftsQuery)
	}

	const result = db.prepare(query).get(...queryParams)
	return result.count
}

async function getItemDetails(params) {
	const db = getDatabase()
	const { item_code, warehouse, price_list, pos_profile } = params

	const item = db.prepare("SELECT * FROM items WHERE item_code = ?").get(item_code)
	if (!item) throw new FrappeError(`Item ${item_code} not found`)

	const result = { ...item }

	// Get price
	const pl = price_list || _getDefaultPriceList(db, pos_profile)
	if (pl) {
		const price = db.prepare(
			"SELECT price_list_rate FROM item_prices WHERE price_list = ? AND item_code = ?"
		).get(pl, item_code)
		result.price_list_rate = price?.price_list_rate || 0
		result.rate = price?.price_list_rate || 0
	}

	// Get UOMs
	result.uoms = db.prepare("SELECT uom, conversion_factor FROM item_uoms WHERE item_code = ?").all(item_code)

	// Get stock
	if (warehouse) {
		const stock = db.prepare("SELECT actual_qty FROM stock WHERE item_code = ? AND warehouse = ?").get(item_code, warehouse)
		result.actual_qty = stock?.actual_qty || 0
	}

	// Get barcodes
	result.barcodes = db.prepare("SELECT barcode, barcode_type FROM item_barcodes WHERE item_code = ?").all(item_code)

	// Get batches (if batch-tracked)
	if (item.has_batch_no) {
		result.batches = db.prepare(`
			SELECT batch_id, qty, expiry_date, manufacturing_date
			FROM batches
			WHERE item_code = ? AND disabled = 0 AND qty > 0
			${warehouse ? "AND warehouse = ?" : ""}
			ORDER BY expiry_date ASC
		`).all(...(warehouse ? [item_code, warehouse] : [item_code]))
	}

	// Get serial numbers (if serial-tracked)
	if (item.has_serial_no) {
		result.serial_numbers = db.prepare(`
			SELECT serial_no FROM serial_numbers
			WHERE item_code = ? AND status = 'Active'
			${warehouse ? "AND warehouse = ?" : ""}
		`).all(...(warehouse ? [item_code, warehouse] : [item_code])).map(s => s.serial_no)
	}

	return result
}

async function getItemGroups(params) {
	const db = getDatabase()
	const { pos_profile } = params

	// Get all item groups with hierarchy
	const groups = db.prepare(`
		SELECT name, is_group, parent_item_group, lft, rgt, image
		FROM item_groups
		ORDER BY lft
	`).all()

	// Build hierarchy — attach child_groups array
	for (const group of groups) {
		group.child_groups = groups
			.filter(g => g.parent_item_group === group.name)
			.map(g => g.name)
	}

	return groups
}

async function searchByBarcode(params) {
	const db = getDatabase()
	const { barcode } = params

	if (!barcode) throw new FrappeError("Barcode is required")

	const barcodeRow = db.prepare(
		"SELECT item_code FROM item_barcodes WHERE barcode = ?"
	).get(barcode)

	if (!barcodeRow) {
		return { found: false, item_code: null }
	}

	const item = db.prepare(`
		SELECT item_code, item_name, description, stock_uom, image,
			   is_stock_item, has_batch_no, has_serial_no, item_group,
			   brand, has_variants, variant_of
		FROM items WHERE item_code = ?
	`).get(barcodeRow.item_code)

	if (!item) return { found: false, item_code: null }

	return { found: true, ...item }
}

async function getItemStock(params) {
	const db = getDatabase()
	const { item_code, warehouse } = params

	if (!item_code) throw new FrappeError("Item code is required")

	if (warehouse) {
		const stock = db.prepare(
			"SELECT actual_qty FROM stock WHERE item_code = ? AND warehouse = ?"
		).get(item_code, warehouse)
		return stock?.actual_qty || 0
	}

	// Sum across all warehouses
	const result = db.prepare(
		"SELECT SUM(actual_qty) as total FROM stock WHERE item_code = ?"
	).get(item_code)
	return result?.total || 0
}

async function getBatchSerialDetails(params) {
	const db = getDatabase()
	const { item_code, warehouse } = params

	const result = { batches: [], serial_numbers: [] }

	const item = db.prepare("SELECT has_batch_no, has_serial_no FROM items WHERE item_code = ?").get(item_code)
	if (!item) return result

	if (item.has_batch_no) {
		result.batches = db.prepare(`
			SELECT batch_id, qty, expiry_date, manufacturing_date
			FROM batches
			WHERE item_code = ? AND disabled = 0 AND qty > 0
			${warehouse ? "AND warehouse = ?" : ""}
		`).all(...(warehouse ? [item_code, warehouse] : [item_code]))
	}

	if (item.has_serial_no) {
		result.serial_numbers = db.prepare(`
			SELECT serial_no FROM serial_numbers
			WHERE item_code = ? AND status = 'Active'
			${warehouse ? "AND warehouse = ?" : ""}
		`).all(...(warehouse ? [item_code, warehouse] : [item_code])).map(s => s.serial_no)
	}

	return result
}

async function getItemVariants(params) {
	const db = getDatabase()
	const { item_code } = params

	return db.prepare(`
		SELECT item_code, item_name, description, stock_uom, image,
			   item_group, brand
		FROM items
		WHERE variant_of = ? AND disabled = 0
	`).all(item_code)
}

async function getStockQuantities(params) {
	const db = getDatabase()
	const { items: itemCodes, warehouse } = params

	const codes = typeof itemCodes === "string" ? JSON.parse(itemCodes) : itemCodes
	if (!codes?.length) return {}

	const result = {}
	for (const code of codes) {
		const stock = db.prepare(
			"SELECT actual_qty FROM stock WHERE item_code = ? AND warehouse = ?"
		).get(code, warehouse)
		result[code] = stock?.actual_qty || 0
	}
	return result
}

async function getItemWarehouseAvailability(params) {
	const db = getDatabase()
	const { item_code } = params

	return db.prepare(`
		SELECT s.warehouse, s.actual_qty, w.warehouse_name
		FROM stock s
		LEFT JOIN warehouses w ON s.warehouse = w.name
		WHERE s.item_code = ? AND s.actual_qty > 0
		ORDER BY s.actual_qty DESC
	`).all(item_code)
}

async function getProductBundleAvailability(params) {
	// Product bundles are not commonly used in offline POS
	// Stub that returns available
	return { available: true, qty: 999 }
}

// Helpers

function _getDefaultPriceList(db, posProfile) {
	if (!posProfile) return null
	const profile = db.prepare("SELECT selling_price_list FROM pos_profiles WHERE name = ?").get(posProfile)
	return profile?.selling_price_list || null
}

module.exports = {
	getItems,
	getItemsBulk,
	getItemsCount,
	getItemDetails,
	getItemGroups,
	searchByBarcode,
	getItemStock,
	getBatchSerialDetails,
	getItemVariants,
	getStockQuantities,
	getItemWarehouseAvailability,
	getProductBundleAvailability,
}
