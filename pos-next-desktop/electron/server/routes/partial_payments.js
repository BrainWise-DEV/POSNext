const { getDatabase } = require("../db/connection")

/**
 * Partial Payments API - replaces pos_next.api.partial_payments
 * Local partial payment tracking.
 */

async function getPartialPaidInvoices(params) {
	const db = getDatabase()
	const { pos_profile, start = 0, page_length = 20 } = params

	let query = "SELECT * FROM invoices WHERE outstanding_amount > 0 AND docstatus = 1"
	const queryParams = []

	if (pos_profile) {
		query += " AND pos_profile = ?"
		queryParams.push(pos_profile)
	}

	query += " ORDER BY posting_date DESC LIMIT ? OFFSET ?"
	queryParams.push(page_length, start)

	return db.prepare(query).all(...queryParams)
}

async function getUnpaidInvoices(params) {
	return getPartialPaidInvoices(params)
}

async function getPartialPaymentDetails(params) {
	const db = getDatabase()
	const { invoice_name } = params

	const invoice = db.prepare("SELECT * FROM invoices WHERE name = ?").get(invoice_name)
	if (!invoice) return null

	invoice.payments = db.prepare(
		"SELECT * FROM invoice_payments WHERE invoice_name = ?"
	).all(invoice_name)

	return invoice
}

async function addPaymentToPartialInvoice(params) {
	const db = getDatabase()
	const { invoice_name, mode_of_payment, amount } = params

	db.prepare(`
		INSERT INTO invoice_payments (invoice_name, mode_of_payment, amount)
		VALUES (?, ?, ?)
	`).run(invoice_name, mode_of_payment, amount)

	// Update outstanding amount
	db.prepare(`
		UPDATE invoices SET
			paid_amount = paid_amount + ?,
			outstanding_amount = outstanding_amount - ?
		WHERE name = ?
	`).run(amount, amount, invoice_name)

	return db.prepare("SELECT * FROM invoices WHERE name = ?").get(invoice_name)
}

async function getPartialPaymentSummary(params) {
	const db = getDatabase()
	const { pos_profile } = params

	const result = db.prepare(`
		SELECT COUNT(*) as count, SUM(outstanding_amount) as total_outstanding
		FROM invoices WHERE outstanding_amount > 0 AND docstatus = 1
		${pos_profile ? "AND pos_profile = ?" : ""}
	`).get(...(pos_profile ? [pos_profile] : []))

	return result || { count: 0, total_outstanding: 0 }
}

async function getUnpaidSummary(params) {
	return getPartialPaymentSummary(params)
}

module.exports = {
	getPartialPaidInvoices,
	getUnpaidInvoices,
	getPartialPaymentDetails,
	addPaymentToPartialInvoice,
	getPartialPaymentSummary,
	getUnpaidSummary,
}
