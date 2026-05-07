/**
 * Quick Amounts Composable
 * Generates suggested payment amounts based on remaining balance
 */

import { computed } from "vue"
import { roundCurrency } from "@/utils/currency"

/**
 * Create quick amounts suggestions based on remaining amount
 * @param {ComputedRef<number>} remainingAmount - Remaining amount to pay
 * @param {ComputedRef<boolean>} isCash - Whether the selected payment method is cash
 * @returns {Object} Computed quick amounts array
 */
export function useQuickAmounts(remainingAmount, isCash) {
	/**
	 * Generate smart quick amount suggestions
	 * - Cash: starts with ceil (whole denomination), since cash is physical
	 * - Non-cash: starts with exact fractional amount (digital transfer)
	 * - Adds rounded amounts based on common denominations
	 * - Maintains meaningful spacing between suggestions
	 */
	const quickAmounts = computed(() => {
		const remaining = remainingAmount.value
		if (remaining <= 0) {
			return [10, 20, 50, 100]
		}

		const cash = isCash ? isCash.value : true
		const amounts = new Set()
		// Cash payments use ceil (physical denominations), non-cash use exact amount
		const exactAmount = cash ? Math.ceil(remaining) : roundCurrency(remaining)

		// Always include the primary amount first
		amounts.add(exactAmount)

		// Determine a step size based on the remaining amount scale
		const getSuggestionStep = (value) => {
			if (value < 50) return 5
			if (value < 200) return 10
			if (value < 1000) return 20
			if (value < 10000) return 100
			if (value < 50000) return 500
			return 1000
		}

		const step = getSuggestionStep(remaining)
		let nextAmount = Math.ceil((exactAmount + 1) / step) * step

		while (amounts.size < 4) {
			amounts.add(nextAmount)
			nextAmount += step
		}

		return Array.from(amounts)
			.filter((amt) => amt > 0)
			.sort((a, b) => a - b)
			.slice(0, 4)
	})

	return {
		quickAmounts,
	}
}
