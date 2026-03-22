const { getDatabase } = require("../db/connection")

/**
 * Push Engine - Uploads local data to ERPNext.
 *
 * Handles:
 * - Invoice sync (with offline_id deduplication)
 * - New customer sync
 * - Shift data sync
 */

/**
 * Push unsynced invoices to ERPNext.
 * Uses the existing submit_invoice endpoint which handles offline_id dedup.
 */
async function pushInvoices(config, apiFetch) {
	const db = getDatabase()

	const unsyncedInvoices = db.prepare(`
		SELECT * FROM invoices
		WHERE sync_status = 'local' AND docstatus = 1
		ORDER BY created_at ASC
	`).all()

	if (!unsyncedInvoices.length) {
		console.log("[Sync] No invoices to push")
		return { pushed: 0 }
	}

	console.log(`[Sync] Pushing ${unsyncedInvoices.length} invoices...`)
	let pushed = 0
	let failed = 0

	for (const invoice of unsyncedInvoices) {
		try {
			// Mark as syncing
			db.prepare("UPDATE invoices SET sync_status = 'syncing' WHERE name = ?").run(invoice.name)

			// Get full invoice data
			const items = db.prepare("SELECT * FROM invoice_items WHERE invoice_name = ? ORDER BY idx").all(invoice.name)
			const payments = db.prepare("SELECT * FROM invoice_payments WHERE invoice_name = ? ORDER BY idx").all(invoice.name)
			const taxes = db.prepare("SELECT * FROM invoice_taxes WHERE invoice_name = ? ORDER BY idx").all(invoice.name)

			// Build the invoice payload matching what the server expects
			const invoiceData = {
				customer: invoice.customer,
				customer_name: invoice.customer_name,
				pos_profile: invoice.pos_profile,
				company: invoice.company,
				currency: invoice.currency,
				posting_date: invoice.posting_date,
				posting_time: invoice.posting_time,
				is_pos: 1,
				is_return: invoice.is_return,
				return_against: invoice.return_against,
				update_stock: 1,
				total: invoice.total,
				net_total: invoice.net_total,
				grand_total: invoice.grand_total,
				rounded_total: invoice.rounded_total,
				rounding_adjustment: invoice.rounding_adjustment,
				discount_amount: invoice.discount_amount,
				additional_discount_percentage: invoice.additional_discount_percentage,
				write_off_amount: invoice.write_off_amount,
				paid_amount: invoice.paid_amount,
				outstanding_amount: invoice.outstanding_amount,
				change_amount: invoice.change_amount,
				coupon_code: invoice.coupon_code,
				taxes_and_charges: invoice.taxes_and_charges,
				items: items.map(i => ({
					item_code: i.item_code,
					item_name: i.item_name,
					qty: i.qty,
					rate: i.rate,
					price_list_rate: i.price_list_rate,
					discount_percentage: i.discount_percentage,
					discount_amount: i.discount_amount,
					amount: i.amount,
					net_amount: i.net_amount,
					uom: i.uom,
					stock_uom: i.stock_uom,
					conversion_factor: i.conversion_factor,
					warehouse: i.warehouse,
					batch_no: i.batch_no,
					serial_no: i.serial_no,
					is_rate_manually_edited: i.is_rate_manually_edited,
				})),
				payments: payments.map(p => ({
					mode_of_payment: p.mode_of_payment,
					amount: p.amount,
					account: p.account,
					type: p.type,
				})),
				taxes: taxes.map(t => ({
					account_head: t.account_head,
					charge_type: t.charge_type,
					rate: t.rate,
					tax_amount: t.tax_amount,
					description: t.description,
					included_in_print_rate: t.included_in_print_rate,
				})),
			}

			// Submit to ERPNext using the existing offline_id deduplication
			const result = await apiFetch(config, "pos_next.api.invoices.submit_invoice", {
				invoice: JSON.stringify(invoiceData),
				offline_id: invoice.offline_id || invoice.name,
			})

			// Mark as synced
			const serverName = result?.name || result
			db.prepare(`
				UPDATE invoices SET
					sync_status = 'synced',
					server_name = ?,
					synced_at = ?,
					sync_error = NULL
				WHERE name = ?
			`).run(serverName, new Date().toISOString(), invoice.name)

			// Log sync
			db.prepare(`
				INSERT INTO sync_log (entity_type, entity_name, direction, status, synced_at)
				VALUES ('invoice', ?, 'push', 'success', ?)
			`).run(invoice.name, new Date().toISOString())

			pushed++
		} catch (error) {
			console.error(`[Sync] Failed to push invoice ${invoice.name}:`, error.message)

			db.prepare(`
				UPDATE invoices SET sync_status = 'failed', sync_error = ? WHERE name = ?
			`).run(error.message, invoice.name)

			db.prepare(`
				INSERT INTO sync_log (entity_type, entity_name, direction, status, error_message, synced_at)
				VALUES ('invoice', ?, 'push', 'failed', ?, ?)
			`).run(invoice.name, error.message, new Date().toISOString())

			failed++
		}
	}

	console.log(`[Sync] Invoices pushed: ${pushed}, failed: ${failed}`)
	return { pushed, failed }
}

/**
 * Push locally-created customers to ERPNext.
 */
async function pushCustomers(config, apiFetch) {
	const db = getDatabase()

	const localCustomers = db.prepare(
		"SELECT * FROM customers WHERE created_locally = 1 AND synced_at IS NULL"
	).all()

	if (!localCustomers.length) return { pushed: 0 }

	console.log(`[Sync] Pushing ${localCustomers.length} new customers...`)
	let pushed = 0

	for (const customer of localCustomers) {
		try {
			const result = await apiFetch(config, "pos_next.api.customers.create_customer", {
				customer_name: customer.customer_name,
				mobile_no: customer.mobile_no,
				email_id: customer.email_id,
				customer_group: customer.customer_group,
				territory: customer.territory,
				customer_type: customer.customer_type,
			})

			// Update local record with server name
			const serverName = result?.name || result
			db.prepare(`
				UPDATE customers SET synced_at = ?, name = ? WHERE name = ?
			`).run(new Date().toISOString(), serverName, customer.name)

			// Also update any invoices that reference the old local name
			db.prepare(
				"UPDATE invoices SET customer = ? WHERE customer = ?"
			).run(serverName, customer.name)

			pushed++
		} catch (error) {
			console.error(`[Sync] Failed to push customer ${customer.name}:`, error.message)
		}
	}

	return { pushed }
}

/**
 * Push shift data to ERPNext.
 */
async function pushShifts(config, apiFetch) {
	const db = getDatabase()

	const unsyncedShifts = db.prepare(
		"SELECT * FROM pos_shifts WHERE synced_to_server = 0"
	).all()

	if (!unsyncedShifts.length) return { pushed: 0 }

	console.log(`[Sync] Pushing ${unsyncedShifts.length} shifts...`)
	let pushed = 0

	for (const shift of unsyncedShifts) {
		try {
			const details = db.prepare(
				"SELECT * FROM pos_shift_details WHERE shift_name = ?"
			).all(shift.name)

			// For open shifts, create on server
			if (shift.status === "Open") {
				const openingDetails = details.filter(d => d.detail_type === "opening")

				await apiFetch(config, "pos_next.api.shifts.create_opening_shift", {
					pos_profile: shift.pos_profile,
					company: shift.company,
					balance_details: JSON.stringify(openingDetails.map(d => ({
						mode_of_payment: d.mode_of_payment,
						opening_amount: d.amount,
					}))),
				})
			}

			db.prepare("UPDATE pos_shifts SET synced_to_server = 1 WHERE name = ?").run(shift.name)
			pushed++
		} catch (error) {
			console.error(`[Sync] Failed to push shift ${shift.name}:`, error.message)
		}
	}

	return { pushed }
}

module.exports = { pushInvoices, pushCustomers, pushShifts }
