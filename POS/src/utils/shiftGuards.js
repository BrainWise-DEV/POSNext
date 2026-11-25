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

function t(text, args) {
	const translate = globalThis.__
	if (typeof translate === "function") return translate(text, args)
	if (!args) return text
	return text.replace(/{(\d+)}/g, (match, n) => (args[n] !== undefined ? args[n] : match))
}

/**
 * D-R2-18: the drafts still open on the shift (from get_closing_shift_data), for a
 * warning before the cashier closes it, or null when there are none.
 * @returns {{ drafts: Array, title: string, detail: string } | null}
 */
export function openDraftsNotice(closingData) {
	const drafts = Array.isArray(closingData?.open_drafts) ? closingData.open_drafts : []
	if (!drafts.length) return null
	return {
		drafts,
		title: t("{0} draft invoice(s) are still open on this shift", [drafts.length]),
		detail: closingData.open_drafts_deleted_on_close
			? t("They are not in the shift totals and will be deleted when you close the shift.")
			: t("They are not in the shift totals and stay open after you close the shift."),
	}
}

/** The closing shift as the server saves it: without the display-only open drafts. */
export function closingShiftPayload(closingData) {
	const { open_drafts, open_drafts_deleted_on_close, ...doc } = closingData || {}
	return doc
}
