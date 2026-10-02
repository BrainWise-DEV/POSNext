/**
 * Shift close guards for POS Sale.
 * Pure predicates so they can be unit-tested without mounting Vue.
 */

/**
 * Refuse shift close while unsynced offline expenses remain.
 * @param {number} pendingExpensesCount
 * @returns {boolean}
 */
export function canCloseShiftWithPendingExpenses(pendingExpensesCount) {
	return !(Number(pendingExpensesCount) > 0)
}
