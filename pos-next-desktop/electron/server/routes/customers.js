const { getDatabase } = require("../db/connection")
const { FrappeError } = require("../frappe-compat")

/**
 * Customers API - replaces pos_next.api.customers
 */

async function getCustomers(params) {
	const db = getDatabase()
	const { search_term, start = 0, page_length = 20 } = params

	let query = "SELECT * FROM customers WHERE disabled = 0"
	const queryParams = []

	if (search_term) {
		query += " AND (customer_name LIKE ? OR name LIKE ? OR mobile_no LIKE ? OR email_id LIKE ?)"
		const term = `%${search_term}%`
		queryParams.push(term, term, term, term)
	}

	query += " ORDER BY customer_name ASC LIMIT ? OFFSET ?"
	queryParams.push(page_length, start)

	return db.prepare(query).all(...queryParams)
}

async function createCustomer(params) {
	const db = getDatabase()
	const { customer_name, mobile_no, email_id, customer_group, territory, customer_type } = params

	if (!customer_name) throw new FrappeError("Customer name is required")

	// Generate a local name
	const name = `CUST-LOCAL-${Date.now()}`

	db.prepare(`
		INSERT INTO customers (name, customer_name, mobile_no, email_id,
			customer_group, territory, customer_type, created_locally)
		VALUES (?, ?, ?, ?, ?, ?, ?, 1)
	`).run(
		name, customer_name, mobile_no || null, email_id || null,
		customer_group || "Individual", territory || "All Territories",
		customer_type || "Individual"
	)

	return db.prepare("SELECT * FROM customers WHERE name = ?").get(name)
}

async function getCustomerDetails(params) {
	const db = getDatabase()
	const { customer } = params

	const cust = db.prepare("SELECT * FROM customers WHERE name = ?").get(customer)
	if (!cust) throw new FrappeError(`Customer ${customer} not found`)

	return cust
}

module.exports = { getCustomers, createCustomer, getCustomerDetails }
