const { getDatabase } = require("../db/connection")
const { FrappeError } = require("../frappe-compat")

/**
 * Invoices API - replaces pos_next.api.invoices
 * Full local invoice lifecycle: create, update, submit, return.
 */

function _generateInvoiceName(db) {
	const terminalId = db.prepare("SELECT value FROM settings WHERE key = 'terminal_short_id'").get()
	const prefix = `POS-${terminalId?.value || "DESK"}`

	const updateSeries = db.prepare(`
		INSERT INTO naming_series (prefix, current_value) VALUES (?, 1)
		ON CONFLICT(prefix) DO UPDATE SET current_value = current_value + 1
	`)
	updateSeries.run(prefix)

	const series = db.prepare("SELECT current_value FROM naming_series WHERE prefix = ?").get(prefix)
	return `${prefix}-${String(series.current_value).padStart(5, "0")}`
}

function _getCurrentUser(db) {
	const row = db.prepare("SELECT value FROM settings WHERE key = 'current_user'").get()
	return row?.value || "Administrator"
}

async function updateInvoice(params) {
	const db = getDatabase()
	const { invoice } = params
	const data = typeof invoice === "string" ? JSON.parse(invoice) : invoice

	if (!data.name) throw new FrappeError("Invoice name is required")

	const existing = db.prepare("SELECT name FROM invoices WHERE name = ?").get(data.name)
	if (!existing) throw new FrappeError(`Invoice ${data.name} not found`)

	// Update main invoice fields
	db.prepare(`
		UPDATE invoices SET
			customer = ?, customer_name = ?, total = ?, net_total = ?,
			grand_total = ?, rounded_total = ?, rounding_adjustment = ?,
			discount_amount = ?, additional_discount_percentage = ?,
			write_off_amount = ?, paid_amount = ?, outstanding_amount = ?,
			change_amount = ?, coupon_code = ?, data_json = ?
		WHERE name = ?
	`).run(
		data.customer, data.customer_name, data.total || 0, data.net_total || 0,
		data.grand_total || 0, data.rounded_total, data.rounding_adjustment || 0,
		data.discount_amount || 0, data.additional_discount_percentage || 0,
		data.write_off_amount || 0, data.paid_amount || 0, data.outstanding_amount || 0,
		data.change_amount || 0, data.coupon_code, JSON.stringify(data),
		data.name
	)

	// Replace items
	if (data.items) {
		db.prepare("DELETE FROM invoice_items WHERE invoice_name = ?").run(data.name)
		const insertItem = db.prepare(`
			INSERT INTO invoice_items (invoice_name, item_code, item_name, qty, rate,
				price_list_rate, discount_percentage, discount_amount, amount, net_amount,
				uom, stock_uom, conversion_factor, warehouse, batch_no, serial_no,
				is_rate_manually_edited, original_rate, pricing_rules, idx)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		`)
		for (const item of data.items) {
			insertItem.run(
				data.name, item.item_code, item.item_name, item.qty || 0, item.rate || 0,
				item.price_list_rate || 0, item.discount_percentage || 0, item.discount_amount || 0,
				item.amount || 0, item.net_amount || 0, item.uom, item.stock_uom,
				item.conversion_factor || 1, item.warehouse, item.batch_no, item.serial_no,
				item.is_rate_manually_edited || 0, item.original_rate,
				JSON.stringify(item.pricing_rules || []), item.idx || 0
			)
		}
	}

	// Replace payments
	if (data.payments) {
		db.prepare("DELETE FROM invoice_payments WHERE invoice_name = ?").run(data.name)
		const insertPayment = db.prepare(`
			INSERT INTO invoice_payments (invoice_name, mode_of_payment, amount, account, type, idx)
			VALUES (?, ?, ?, ?, ?, ?)
		`)
		for (const payment of data.payments) {
			insertPayment.run(
				data.name, payment.mode_of_payment, payment.amount || 0,
				payment.account, payment.type, payment.idx || 0
			)
		}
	}

	return db.prepare("SELECT * FROM invoices WHERE name = ?").get(data.name)
}

async function submitInvoice(params) {
	const db = getDatabase()
	const { invoice, offline_id } = params
	const data = typeof invoice === "string" ? JSON.parse(invoice) : invoice

	// Deduplication check
	if (offline_id) {
		const existing = db.prepare("SELECT name FROM invoices WHERE offline_id = ?").get(offline_id)
		if (existing) return existing
	}

	const invoiceName = data.name || _generateInvoiceName(db)
	const now = new Date()
	const postingDate = data.posting_date || now.toISOString().split("T")[0]
	const postingTime = data.posting_time || now.toTimeString().split(" ")[0]

	// Get open shift
	const user = _getCurrentUser(db)
	const openShift = db.prepare(
		"SELECT name FROM pos_shifts WHERE user = ? AND status = 'Open' ORDER BY period_start_date DESC LIMIT 1"
	).get(user)

	const submitTransaction = db.transaction(() => {
		// Insert invoice
		db.prepare(`
			INSERT INTO invoices (
				name, offline_id, customer, customer_name, pos_profile, company, currency,
				posting_date, posting_time, is_pos, is_return, return_against, update_stock,
				total, net_total, grand_total, rounded_total, rounding_adjustment,
				discount_amount, additional_discount_percentage, write_off_amount,
				paid_amount, outstanding_amount, change_amount,
				docstatus, status, sync_status, created_at,
				coupon_code, pos_opening_shift, branch, taxes_and_charges, data_json
			) VALUES (
				?, ?, ?, ?, ?, ?, ?,
				?, ?, 1, ?, ?, 1,
				?, ?, ?, ?, ?,
				?, ?, ?,
				?, ?, ?,
				1, 'Paid', 'local', ?,
				?, ?, ?, ?, ?
			)
		`).run(
			invoiceName, offline_id || null,
			data.customer, data.customer_name,
			data.pos_profile, data.company, data.currency,
			postingDate, postingTime,
			data.is_return || 0, data.return_against || null,
			data.total || 0, data.net_total || 0,
			data.grand_total || 0, data.rounded_total || null, data.rounding_adjustment || 0,
			data.discount_amount || 0, data.additional_discount_percentage || 0, data.write_off_amount || 0,
			data.paid_amount || 0, data.outstanding_amount || 0, data.change_amount || 0,
			now.toISOString(),
			data.coupon_code || null, openShift?.name || data.pos_opening_shift || null,
			data.branch || null, data.taxes_and_charges || null,
			JSON.stringify(data)
		)

		// Insert items
		const insertItem = db.prepare(`
			INSERT INTO invoice_items (invoice_name, item_code, item_name, qty, rate,
				price_list_rate, discount_percentage, discount_amount, amount, net_amount,
				uom, stock_uom, conversion_factor, warehouse, batch_no, serial_no,
				is_rate_manually_edited, original_rate, pricing_rules, idx)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		`)

		for (const item of (data.items || [])) {
			insertItem.run(
				invoiceName, item.item_code, item.item_name, item.qty || 0, item.rate || 0,
				item.price_list_rate || 0, item.discount_percentage || 0, item.discount_amount || 0,
				item.amount || 0, item.net_amount || 0, item.uom, item.stock_uom,
				item.conversion_factor || 1, item.warehouse, item.batch_no || null, item.serial_no || null,
				item.is_rate_manually_edited || 0, item.original_rate || null,
				JSON.stringify(item.pricing_rules || []), item.idx || 0
			)

			// Update local stock (decrement)
			if (item.warehouse && !data.is_return) {
				db.prepare(`
					UPDATE stock SET actual_qty = actual_qty - ?
					WHERE item_code = ? AND warehouse = ?
				`).run(item.qty || 0, item.item_code, item.warehouse)
			} else if (item.warehouse && data.is_return) {
				// Returns add stock back
				db.prepare(`
					UPDATE stock SET actual_qty = actual_qty + ?
					WHERE item_code = ? AND warehouse = ?
				`).run(Math.abs(item.qty || 0), item.item_code, item.warehouse)
			}
		}

		// Insert payments
		const insertPayment = db.prepare(`
			INSERT INTO invoice_payments (invoice_name, mode_of_payment, amount, account, type, idx)
			VALUES (?, ?, ?, ?, ?, ?)
		`)
		for (const payment of (data.payments || [])) {
			insertPayment.run(
				invoiceName, payment.mode_of_payment, payment.amount || 0,
				payment.account || null, payment.type || null, payment.idx || 0
			)
		}

		// Insert taxes
		const insertTax = db.prepare(`
			INSERT INTO invoice_taxes (invoice_name, account_head, charge_type, rate,
				tax_amount, total, description, included_in_print_rate, idx)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
		`)
		for (const tax of (data.taxes || [])) {
			insertTax.run(
				invoiceName, tax.account_head, tax.charge_type, tax.rate || 0,
				tax.tax_amount || 0, tax.total || 0, tax.description,
				tax.included_in_print_rate || 0, tax.idx || 0
			)
		}
	})

	submitTransaction()

	// Return the created invoice
	const created = db.prepare("SELECT * FROM invoices WHERE name = ?").get(invoiceName)
	created.items = db.prepare("SELECT * FROM invoice_items WHERE invoice_name = ?").all(invoiceName)
	created.payments = db.prepare("SELECT * FROM invoice_payments WHERE invoice_name = ?").all(invoiceName)
	created.taxes = db.prepare("SELECT * FROM invoice_taxes WHERE invoice_name = ?").all(invoiceName)

	return created
}

async function getInvoice(params) {
	const db = getDatabase()
	const { name } = params

	const invoice = db.prepare("SELECT * FROM invoices WHERE name = ?").get(name)
	if (!invoice) throw new FrappeError(`Invoice ${name} not found`)

	invoice.items = db.prepare("SELECT * FROM invoice_items WHERE invoice_name = ? ORDER BY idx").all(name)
	invoice.payments = db.prepare("SELECT * FROM invoice_payments WHERE invoice_name = ? ORDER BY idx").all(name)
	invoice.taxes = db.prepare("SELECT * FROM invoice_taxes WHERE invoice_name = ? ORDER BY idx").all(name)

	return invoice
}

async function getInvoices(params) {
	const db = getDatabase()
	const { pos_profile, start = 0, page_length = 20, status, posting_date, customer } = params

	let query = "SELECT * FROM invoices WHERE docstatus = 1"
	const queryParams = []

	if (pos_profile) {
		query += " AND pos_profile = ?"
		queryParams.push(pos_profile)
	}
	if (status) {
		query += " AND status = ?"
		queryParams.push(status)
	}
	if (posting_date) {
		query += " AND posting_date = ?"
		queryParams.push(posting_date)
	}
	if (customer) {
		query += " AND customer = ?"
		queryParams.push(customer)
	}

	query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
	queryParams.push(page_length, start)

	return db.prepare(query).all(...queryParams)
}

async function getDraftInvoices(params) {
	const db = getDatabase()
	const { pos_profile } = params

	let query = "SELECT * FROM invoices WHERE docstatus = 0"
	const queryParams = []

	if (pos_profile) {
		query += " AND pos_profile = ?"
		queryParams.push(pos_profile)
	}

	query += " ORDER BY created_at DESC"

	const drafts = db.prepare(query).all(...queryParams)

	for (const draft of drafts) {
		draft.items = db.prepare("SELECT * FROM invoice_items WHERE invoice_name = ? ORDER BY idx").all(draft.name)
		draft.payments = db.prepare("SELECT * FROM invoice_payments WHERE invoice_name = ? ORDER BY idx").all(draft.name)
	}

	return drafts
}

async function deleteInvoice(params) {
	const db = getDatabase()
	const { name } = params

	const invoice = db.prepare("SELECT docstatus FROM invoices WHERE name = ?").get(name)
	if (!invoice) throw new FrappeError(`Invoice ${name} not found`)
	if (invoice.docstatus === 1) throw new FrappeError("Cannot delete a submitted invoice")

	const deleteTransaction = db.transaction(() => {
		db.prepare("DELETE FROM invoice_items WHERE invoice_name = ?").run(name)
		db.prepare("DELETE FROM invoice_payments WHERE invoice_name = ?").run(name)
		db.prepare("DELETE FROM invoice_taxes WHERE invoice_name = ?").run(name)
		db.prepare("DELETE FROM invoices WHERE name = ?").run(name)
	})

	deleteTransaction()
	return { success: true }
}

async function cleanupOldDrafts(params) {
	const db = getDatabase()
	const { days_old = 7, pos_profile } = params

	const cutoff = new Date()
	cutoff.setDate(cutoff.getDate() - days_old)

	let query = "SELECT name FROM invoices WHERE docstatus = 0 AND is_pos = 1 AND created_at < ?"
	const queryParams = [cutoff.toISOString()]

	if (pos_profile) {
		query += " AND pos_profile = ?"
		queryParams.push(pos_profile)
	}

	const oldDrafts = db.prepare(query).all(...queryParams)

	const cleanup = db.transaction(() => {
		for (const draft of oldDrafts) {
			db.prepare("DELETE FROM invoice_items WHERE invoice_name = ?").run(draft.name)
			db.prepare("DELETE FROM invoice_payments WHERE invoice_name = ?").run(draft.name)
			db.prepare("DELETE FROM invoice_taxes WHERE invoice_name = ?").run(draft.name)
			db.prepare("DELETE FROM invoices WHERE name = ?").run(draft.name)
		}
	})

	cleanup()
	return { deleted_count: oldDrafts.length }
}

async function getReturnableInvoices(params) {
	const db = getDatabase()
	const { pos_profile, search_term, start = 0, page_length = 20 } = params

	let query = `
		SELECT * FROM invoices
		WHERE docstatus = 1 AND is_return = 0 AND status = 'Paid'
	`
	const queryParams = []

	if (pos_profile) {
		query += " AND pos_profile = ?"
		queryParams.push(pos_profile)
	}
	if (search_term) {
		query += " AND (name LIKE ? OR customer_name LIKE ?)"
		queryParams.push(`%${search_term}%`, `%${search_term}%`)
	}

	query += " ORDER BY posting_date DESC LIMIT ? OFFSET ?"
	queryParams.push(page_length, start)

	return db.prepare(query).all(...queryParams)
}

async function searchInvoiceByNumber(params) {
	const db = getDatabase()
	const { invoice_number } = params

	const invoice = db.prepare("SELECT * FROM invoices WHERE name = ?").get(invoice_number)
	if (!invoice) return null

	invoice.items = db.prepare("SELECT * FROM invoice_items WHERE invoice_name = ?").all(invoice_number)
	invoice.payments = db.prepare("SELECT * FROM invoice_payments WHERE invoice_name = ?").all(invoice_number)

	return invoice
}

async function checkInvoiceReturnValidity(params) {
	const { invoice_name } = params
	const db = getDatabase()

	const invoice = db.prepare("SELECT * FROM invoices WHERE name = ? AND docstatus = 1").get(invoice_name)
	if (!invoice) return { valid: false, message: "Invoice not found" }
	if (invoice.is_return) return { valid: false, message: "Cannot return a return invoice" }

	// Check if already returned
	const returnInvoice = db.prepare(
		"SELECT name FROM invoices WHERE return_against = ? AND docstatus = 1"
	).get(invoice_name)

	if (returnInvoice) return { valid: false, message: "Invoice already returned" }

	return { valid: true }
}

async function getInvoiceForReturn(params) {
	return getInvoice(params)
}

async function prepareReturnInvoice(params) {
	const db = getDatabase()
	const { invoice_name } = params

	const original = await getInvoice({ name: invoice_name })
	if (!original) throw new FrappeError("Original invoice not found")

	// Create return data (negate quantities and amounts)
	const returnData = { ...original }
	returnData.name = null
	returnData.is_return = 1
	returnData.return_against = invoice_name

	returnData.items = original.items.map(item => ({
		...item,
		qty: -Math.abs(item.qty),
		amount: -Math.abs(item.amount),
		net_amount: -Math.abs(item.net_amount),
	}))

	return returnData
}

async function searchInvoicesForReturn(params) {
	return getReturnableInvoices(params)
}

async function applyOffers(params) {
	// Simplified: return items as-is without offer modifications
	// Full offer engine would be implemented for production
	const { items } = params
	return { items: typeof items === "string" ? JSON.parse(items) : items }
}

async function validateCartItems(params) {
	const db = getDatabase()
	const { items, warehouse } = params

	const itemsList = typeof items === "string" ? JSON.parse(items) : items
	const errors = []

	for (const item of (itemsList || [])) {
		const dbItem = db.prepare("SELECT disabled FROM items WHERE item_code = ?").get(item.item_code)
		if (!dbItem) {
			errors.push(`Item ${item.item_code} not found`)
		} else if (dbItem.disabled) {
			errors.push(`Item ${item.item_code} is disabled`)
		}
	}

	return { valid: errors.length === 0, errors }
}

async function validateReturnItems(params) {
	return { valid: true, errors: [] }
}

async function checkOfflineInvoiceSynced(params) {
	const db = getDatabase()
	const { offline_id } = params

	const invoice = db.prepare("SELECT name, sync_status FROM invoices WHERE offline_id = ?").get(offline_id)
	if (!invoice) return { synced: false, exists: false }

	return { synced: invoice.sync_status === "synced", exists: true, name: invoice.name }
}

async function getBatchSerialDataForItems(params) {
	const db = getDatabase()
	const { items: itemCodes, warehouse } = params

	const codes = typeof itemCodes === "string" ? JSON.parse(itemCodes) : itemCodes
	const result = {}

	for (const code of (codes || [])) {
		const item = db.prepare("SELECT has_batch_no, has_serial_no FROM items WHERE item_code = ?").get(code)
		if (!item) continue

		result[code] = { batches: [], serial_numbers: [] }

		if (item.has_batch_no) {
			result[code].batches = db.prepare(`
				SELECT batch_id, qty, expiry_date FROM batches
				WHERE item_code = ? AND disabled = 0 AND qty > 0
				${warehouse ? "AND warehouse = ?" : ""}
			`).all(...(warehouse ? [code, warehouse] : [code]))
		}

		if (item.has_serial_no) {
			result[code].serial_numbers = db.prepare(`
				SELECT serial_no FROM serial_numbers
				WHERE item_code = ? AND status = 'Active'
				${warehouse ? "AND warehouse = ?" : ""}
			`).all(...(warehouse ? [code, warehouse] : [code])).map(s => s.serial_no)
		}
	}

	return result
}

module.exports = {
	updateInvoice,
	submitInvoice,
	getInvoice,
	getInvoices,
	getDraftInvoices,
	deleteInvoice,
	cleanupOldDrafts,
	getReturnableInvoices,
	searchInvoiceByNumber,
	checkInvoiceReturnValidity,
	getInvoiceForReturn,
	prepareReturnInvoice,
	searchInvoicesForReturn,
	applyOffers,
	validateCartItems,
	validateReturnItems,
	checkOfflineInvoiceSynced,
	getBatchSerialDataForItems,
}
