/**
 * Stock Validation Utility
 * Checks item stock availability before adding to cart
 */

import { call } from "frappe-ui";

/**
 * Check if item has sufficient stock
 * @param {Object} params - Validation parameters
 * @param {string} params.itemCode - Item code to check
 * @param {number} params.qty - Quantity requested
 * @param {string} params.warehouse - Warehouse to check
 * @param {number} params.actualQty - Actual available quantity from item
 * @returns {Object} - { available: boolean, actualQty: number }
 */
export function checkStockAvailability({ itemCode, qty, warehouse, actualQty = null }) {
	// If actual quantity is provided (from item data), use it
	if (actualQty !== null && actualQty !== undefined) {
		const available = actualQty >= qty;
		return {
			available,
			actualQty: actualQty,
		};
	}

	// If no stock data available, allow the transaction
	// Backend will validate on submit anyway
	return {
		available: true,
		actualQty: qty,
	};
}

/**
 * Get item stock from Frappe API
 * @param {string} itemCode - Item code
 * @param {string} warehouse - Warehouse
 * @returns {Promise<number>} - Available quantity
 */
export async function getItemStock(itemCode, warehouse) {
	try {
		const result = await call("frappe.client.get_value", {
			doctype: "Bin",
			filters: {
				item_code: itemCode,
				warehouse: warehouse,
			},
			fieldname: "actual_qty",
		});

		return Number.parseFloat(result?.actual_qty || 0);
	} catch (error) {
		console.warn("Failed to fetch stock:", error);
		return 0;
	}
}

/**
 * Format stock error message for user
 * @param {string} itemName - Item name
 * @param {number} requested - Requested quantity
 * @param {number} available - Available quantity
 * @param {string} warehouse - Warehouse name
 * @returns {string} - Formatted error message
 */
export function formatStockError(itemName, requested, available, warehouse) {
	const unit = requested === 1 ? "unit" : "units";
	const availableUnit = available === 1 ? "unit" : "units";

	if (available === 0) {
		return `"${itemName}" is out of stock in warehouse "${warehouse}".\n\nPlease check another warehouse or restock this item.`;
	}

	return `Not enough stock for "${itemName}".\n\nYou requested ${requested} ${unit}, but only ${available} ${availableUnit} available in "${warehouse}".\n\nPlease reduce the quantity or check another warehouse.`;
}

/**
 * Validate cart items stock before submission
 * @param {Array} items - Cart items
 * @param {string} warehouse - Warehouse to check
 * @returns {Promise<Object>} - { valid: boolean, errors: Array }
 */
export async function validateCartStock(items, warehouse) {
	const errors = [];

	for (const item of items) {
		const result = await checkStockAvailability({
			itemCode: item.item_code,
			qty: item.quantity,
			warehouse: item.warehouse || warehouse,
			uom: item.uom,
		});

		if (!result.available) {
			errors.push({
				itemCode: item.item_code,
				itemName: item.item_name,
				requested: item.quantity,
				available: result.actualQty,
				warehouse: item.warehouse || warehouse,
				message: formatStockError(
					item.item_name,
					item.quantity,
					result.actualQty,
					item.warehouse || warehouse,
				),
			});
		}
	}

	return {
		valid: errors.length === 0,
		errors,
	};
}
