/**
 * Stock Composable
 *
 * Provides centralized stock-related utilities including stock status
 * badge styling based on quantity levels.
 *
 * Usage:
 * import { useStock } from '@/composables/useStock'
 * const { getStockStatus } = useStock()
 * const status = getStockStatus(item.actual_qty)
 * const itemStatus = getItemStockStatus(item) // threshold from the item's own levels
 */

// Low-stock threshold when the item carries no safety stock or reorder level
export const DEFAULT_LOW_STOCK_THRESHOLD = 5;

/**
 * Low-stock threshold for one item: its safety stock, else its reorder level,
 * else DEFAULT_LOW_STOCK_THRESHOLD.
 *
 * @param {Object} item - Item row (safety_stock / reorder_level are optional)
 * @returns {number} Quantity at or below which the item counts as low stock
 */
export function getLowStockThreshold(item) {
	return (
		[item?.safety_stock, item?.reorder_level].map(Number).find((v) => v > 0) ??
		DEFAULT_LOW_STOCK_THRESHOLD
	);
}

export function useStock() {
	/**
	 * Get stock status information based on quantity
	 *
	 * @param {number|null|undefined} qty - The stock quantity
	 * @param {number} lowStockThreshold - Threshold for low stock warning (default: DEFAULT_LOW_STOCK_THRESHOLD)
	 * @returns {Object} Stock status with level, color, textColor, and label
	 */
	function getStockStatus(qty, lowStockThreshold = DEFAULT_LOW_STOCK_THRESHOLD) {
		const quantity = Math.floor(qty !== undefined && qty !== null ? qty : 0);

		if (quantity < 0) {
			return {
				level: "negative",
				color: "bg-red-700",
				textColor: "text-white",
				label: __("Negative Stock"),
			};
		}

		if (quantity === 0) {
			return {
				level: "out",
				color: "bg-red-700",
				textColor: "text-white",
				label: __("Out of Stock"),
			};
		}

		if (quantity <= lowStockThreshold) {
			return {
				level: "low",
				color: "bg-amber-700",
				textColor: "text-white",
				label: __("Low Stock"),
			};
		}

		return {
			level: "safe",
			color: "bg-green-700",
			textColor: "text-white",
			label: __("In Stock"),
		};
	}

	/**
	 * Stock status for an item row, using its own low-stock threshold
	 *
	 * @param {Object} item - Item with actual_qty or stock_qty
	 * @returns {Object} Same shape as getStockStatus
	 */
	function getItemStockStatus(item) {
		return getStockStatus(item?.actual_qty ?? item?.stock_qty ?? 0, getLowStockThreshold(item));
	}

	return {
		getStockStatus,
		getItemStockStatus,
	};
}
