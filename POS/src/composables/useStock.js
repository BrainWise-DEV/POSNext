/**
 * Stock Composable
 *
 * Provides centralized stock-related utilities including stock status
 * badge styling, display helpers, and visibility logic.
 *
 * Usage:
 * import { useStock } from '@/composables/useStock'
 * const { getStockStatus, shouldShowStockBadge, getDisplayStock } = useStock()
 */

export function useStock() {
	/**
	 * Get stock status information based on quantity
	 *
	 * @param {number|null|undefined} qty - The stock quantity
	 * @param {number} lowStockThreshold - Threshold for low stock warning (default: 10)
	 * @returns {Object} Stock status with level, color, textColor, and label
	 */
	function getStockStatus(qty, lowStockThreshold = 10) {
		const quantity = Math.floor(qty !== undefined && qty !== null ? qty : 0)

		if (quantity < 0) {
			return {
				level: "negative",
				color: "bg-red-500",
				textColor: "text-white",
				label: __("Negative Stock"),
			}
		}

		if (quantity === 0) {
			return {
				level: "out",
				color: "bg-red-500",
				textColor: "text-white",
				label: __("Out of Stock"),
			}
		}

		if (quantity <= lowStockThreshold) {
			return {
				level: "low",
				color: "bg-amber-500",
				textColor: "text-white",
				label: __("Low Stock"),
			}
		}

		return {
			level: "safe",
			color: "bg-green-500",
			textColor: "text-white",
			label: __("In Stock"),
		}
	}

	/**
	 * Determines if stock badge should be displayed for an item.
	 *
	 * Stock badges are hidden for:
	 * - Item templates (has_variants=1) since stock is tracked on individual variants
	 * - Non-stock items that aren't bundles
	 *
	 * @param {Object} item - The item object
	 * @returns {boolean} True if stock badge should be shown
	 */
	function shouldShowStockBadge(item) {
		if (!item) return false
		const isStockTracked = item.is_stock_item || item.is_bundle
		const isTemplate = item.has_variants
		return isStockTracked && !isTemplate
	}

	/**
	 * Gets the stock quantity for display purposes.
	 * Handles null/undefined values and floors the result.
	 *
	 * @param {Object} item - The item object
	 * @returns {number} The floored stock quantity
	 */
	function getDisplayStock(item) {
		return Math.floor(item?.actual_qty ?? item?.stock_qty ?? 0)
	}

	/**
	 * Determines if out-of-stock visual indicators should be shown.
	 * Used for blur effects, overlay icons, etc.
	 *
	 * @param {Object} item - The item object
	 * @returns {boolean} True if out-of-stock indicators should be shown
	 */
	function isOutOfStock(item) {
		return shouldShowStockBadge(item) && getDisplayStock(item) <= 0
	}

	return {
		getStockStatus,
		shouldShowStockBadge,
		getDisplayStock,
		isOutOfStock,
	}
}
