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

	return {
		getStockStatus,
	}
}
