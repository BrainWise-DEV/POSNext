/**
 * Payment Calculations Composable
 * Handles payment totals, remaining amounts, and change calculations
 */

import { computed } from "vue"
import { roundCurrency } from "@/utils/currency"

/**
 * Create payment calculation computed properties
 * @param {Object} options - Configuration options
 * @param {import('vue').Ref<Array>} options.paymentEntries - Reactive payment entries array
 * @param {import('vue').Ref<number>} options.grandTotal - Grand total amount
 * @param {import('vue').Ref<Object>} options.customerBalance - Customer balance object
 * @param {Function} options.getMethodTotal - Function to get total for a payment method
 * @returns {Object} Computed payment calculations
 */
export function usePaymentCalculations({ paymentEntries, grandTotal, customerBalance, getMethodTotal }) {
	/**
	 * Total amount paid across all payment entries
	 */
	const totalPaid = computed(() => {
		const sum = paymentEntries.value.reduce((acc, entry) => acc + (entry.amount || 0), 0)
		return roundCurrency(sum)
	})

	/**
	 * Total available credit from customer balance
	 * Positive = credit available, Negative = outstanding
	 */
	const totalAvailableCredit = computed(() => {
		// Use net_balance: negative means customer has credit, positive means they owe
		// Return negative of net_balance so positive = credit available, negative = outstanding
		return roundCurrency(-customerBalance.value.net_balance)
	})

	/**
	 * Remaining credit after deducting what's already been applied as payment
	 */
	const remainingAvailableCredit = computed(() => {
		const usedCredit = getMethodTotal("Customer Credit")
		const remaining = totalAvailableCredit.value - usedCredit
		return remaining > 0 ? roundCurrency(remaining) : 0
	})

	/**
	 * Amount still remaining to be paid
	 */
	const remainingAmount = computed(() => {
		const remaining = roundCurrency(grandTotal.value) - totalPaid.value
		return remaining > 0 ? roundCurrency(remaining) : 0
	})

	/**
	 * Change amount to return to customer (overpayment)
	 */
	const changeAmount = computed(() => {
		const change = totalPaid.value - roundCurrency(grandTotal.value)
		return change > 0 ? roundCurrency(change) : 0
	})

	return {
		totalPaid,
		totalAvailableCredit,
		remainingAvailableCredit,
		remainingAmount,
		changeAmount,
	}
}
