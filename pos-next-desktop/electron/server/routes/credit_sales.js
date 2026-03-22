const { getDatabase } = require("../db/connection")

/**
 * Credit Sales API - replaces pos_next.api.credit_sales
 * Local credit tracking (limited functionality offline).
 */

async function getCustomerBalance(params) {
	const db = getDatabase()
	const { customer } = params

	const result = db.prepare(`
		SELECT SUM(outstanding_amount) as balance
		FROM invoices WHERE customer = ? AND docstatus = 1 AND outstanding_amount > 0
	`).get(customer)

	return result?.balance || 0
}

async function getAvailableCredit(params) {
	return { available_credit: 0 }
}

async function redeemCustomerCredit() {
	const { FrappeError } = require("../frappe-compat")
	throw new FrappeError("Credit redemption requires internet connection", { httpStatus: 503 })
}

async function cancelCreditJournalEntries() {
	const { FrappeError } = require("../frappe-compat")
	throw new FrappeError("Credit cancellation requires internet connection", { httpStatus: 503 })
}

async function getCreditSaleSummary(params) {
	const db = getDatabase()
	const { customer } = params

	const result = db.prepare(`
		SELECT COUNT(*) as count, SUM(outstanding_amount) as total
		FROM invoices WHERE customer = ? AND docstatus = 1 AND outstanding_amount > 0
	`).get(customer)

	return result || { count: 0, total: 0 }
}

module.exports = {
	getCustomerBalance,
	getAvailableCredit,
	redeemCustomerCredit,
	cancelCreditJournalEntries,
	getCreditSaleSummary,
}
