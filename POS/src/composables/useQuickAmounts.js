/**
 * Quick Amounts Composable
 * Generates suggested payment amounts based on remaining balance
 */

import { computed } from "vue"

/**
 * Create quick amounts suggestions based on remaining amount
 * @param {ComputedRef<number>} remainingAmount - Remaining amount to pay
 * @returns {Object} Computed quick amounts array
 */
export function useQuickAmounts(remainingAmount) {
	/**
	 * Generate smart quick amount suggestions
	 * - Always includes exact amount first
	 * - Adds rounded amounts based on common denominations
	 * - Maintains meaningful spacing between suggestions
	 */
	const quickAmounts = computed(() => {
		const remaining = remainingAmount.value
		if (remaining <= 0) {
			return [10, 20, 50, 100]
		}

		const amounts = new Set()
		const exactAmount = Math.ceil(remaining)

		// Always include exact amount first
		amounts.add(exactAmount)

		// Determine appropriate denominations based on amount size
		// For amounts < 50, use smaller denominations
		// For amounts >= 50, skip to larger denominations for meaningful differences
		let denominations
		if (remaining < 20) {
			denominations = [5, 10, 20, 50]
		} else if (remaining < 100) {
			denominations = [10, 20, 50, 100]
		} else if (remaining < 500) {
			denominations = [50, 100, 200, 500]
		} else if (remaining < 2000) {
			denominations = [100, 200, 500, 1000]
		} else {
			denominations = [500, 1000, 2000, 5000]
		}

		// Minimum gap between suggestions (at least 5% or 5, whichever is larger)
		const minGap = Math.max(5, exactAmount * 0.05)

		// Helper to check if amount is far enough from existing amounts
		const isFarEnough = (newAmt) => {
			for (const existing of amounts) {
				if (Math.abs(newAmt - existing) < minGap) return false
			}
			return true
		}

		// Add round-up amounts for each denomination
		for (const denom of denominations) {
			if (amounts.size >= 4) break

			// Round up to next multiple of this denomination
			const roundedUp = Math.ceil(remaining / denom) * denom

			// Add if it's meaningfully different from exact amount
			if (roundedUp > exactAmount && isFarEnough(roundedUp)) {
				amounts.add(roundedUp)
			}

			// Also add one step higher for convenience (e.g., 350 when remaining is 299)
			if (amounts.size < 4) {
				const oneStepUp = roundedUp + denom
				if (oneStepUp > exactAmount && isFarEnough(oneStepUp)) {
					amounts.add(oneStepUp)
				}
			}
		}

		// Convert to array, sort, and limit to 4
		return Array.from(amounts)
			.filter((amt) => amt > 0)
			.sort((a, b) => a - b)
			.slice(0, 4)
	})

	return {
		quickAmounts,
	}
}
