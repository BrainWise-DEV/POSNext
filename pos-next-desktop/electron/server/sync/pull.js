const { getDatabase } = require("../db/connection")

/**
 * Pull Engine - Downloads data from ERPNext into local SQLite.
 *
 * Two modes:
 * - pullMasterData: Full initial provisioning (first-time setup)
 * - pullDeltaUpdates: Incremental sync using modified timestamps
 */

/**
 * Full master data download for first-time setup.
 * Pulls all data in dependency order.
 */
async function pullMasterData(config, apiFetch, onProgress) {
	const db = getDatabase()
	const steps = [
		{ name: "System Settings", fn: () => pullSystemSettings(db, config, apiFetch) },
		{ name: "Companies", fn: () => pullCompanies(db, config, apiFetch) },
		{ name: "POS Profiles", fn: () => pullPosProfiles(db, config, apiFetch) },
		{ name: "Payment Methods", fn: () => pullPaymentMethods(db, config, apiFetch) },
		{ name: "Tax Templates", fn: () => pullTaxTemplates(db, config, apiFetch) },
		{ name: "Warehouses", fn: () => pullWarehouses(db, config, apiFetch) },
		{ name: "Item Groups", fn: () => pullItemGroups(db, config, apiFetch) },
		{ name: "Items", fn: () => pullItems(db, config, apiFetch, onProgress) },
		{ name: "Item Prices", fn: () => pullItemPrices(db, config, apiFetch) },
		{ name: "Stock", fn: () => pullStock(db, config, apiFetch) },
		{ name: "Customers", fn: () => pullCustomers(db, config, apiFetch) },
		{ name: "Sales Persons", fn: () => pullSalesPersons(db, config, apiFetch) },
		{ name: "Users", fn: () => pullUsers(db, config, apiFetch) },
	]

	for (let i = 0; i < steps.length; i++) {
		const step = steps[i]
		console.log(`[Sync] Pulling ${step.name}... (${i + 1}/${steps.length})`)
		onProgress({ current: i, total: steps.length, phase: `Downloading ${step.name}...` })

		try {
			await step.fn()
		} catch (error) {
			console.error(`[Sync] Error pulling ${step.name}:`, error.message)
			// Continue with other pulls - don't fail entire provisioning
		}
	}

	onProgress({ current: steps.length, total: steps.length, phase: "Complete" })
}

/**
 * Incremental delta sync - only pull records modified since last sync.
 */
async function pullDeltaUpdates(config, apiFetch, onProgress) {
	const db = getDatabase()
	const lastSync = db.prepare("SELECT value FROM settings WHERE key = 'last_sync'").get()?.value

	onProgress({ current: 0, total: 5, phase: "Syncing items..." })
	await pullItems(db, config, apiFetch, onProgress, lastSync)

	onProgress({ current: 1, total: 5, phase: "Syncing stock..." })
	await pullStock(db, config, apiFetch)

	onProgress({ current: 2, total: 5, phase: "Syncing customers..." })
	await pullCustomers(db, config, apiFetch, lastSync)

	onProgress({ current: 3, total: 5, phase: "Syncing prices..." })
	await pullItemPrices(db, config, apiFetch, lastSync)

	onProgress({ current: 4, total: 5, phase: "Syncing profiles..." })
	await pullPosProfiles(db, config, apiFetch)

	onProgress({ current: 5, total: 5, phase: "Done" })
}

// ============================================================================
// Individual Pull Functions
// ============================================================================

async function pullSystemSettings(db, config, apiFetch) {
	const settings = await apiFetch(config, "frappe.client.get_value", {
		doctype: "System Settings",
		fieldname: ["currency_precision", "float_precision", "rounding_method", "number_format"],
	})

	if (settings) {
		const upsert = db.prepare("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)")
		const tx = db.transaction(() => {
			for (const [key, value] of Object.entries(settings)) {
				if (value !== undefined) upsert.run(key, String(value))
			}
		})
		tx()
	}
}

async function pullCompanies(db, config, apiFetch) {
	const companies = await apiFetch(config, "frappe.client.get_list", {
		doctype: "Company",
		fields: ["name", "company_name", "default_currency", "country"],
		limit_page_length: 0,
	})

	const upsert = db.prepare(`
		INSERT OR REPLACE INTO companies (name, company_name, default_currency, country)
		VALUES (?, ?, ?, ?)
	`)

	const tx = db.transaction(() => {
		for (const c of (companies || [])) {
			upsert.run(c.name, c.company_name, c.default_currency, c.country)
		}
	})
	tx()
}

async function pullPosProfiles(db, config, apiFetch) {
	const profiles = await apiFetch(config, "frappe.client.get_list", {
		doctype: "POS Profile",
		fields: ["*"],
		filters: { disabled: 0 },
		limit_page_length: 0,
	})

	const upsertProfile = db.prepare(`
		INSERT OR REPLACE INTO pos_profiles (
			name, company, currency, warehouse, selling_price_list, customer,
			write_off_account, write_off_cost_center, write_off_limit,
			print_format, country, ignore_pricing_rule, disable_rounded_total,
			disabled, taxes_and_charges, branch, data_json
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`)

	const upsertUser = db.prepare(
		"INSERT OR IGNORE INTO pos_profile_users (pos_profile, user) VALUES (?, ?)"
	)

	const tx = db.transaction(() => {
		for (const p of (profiles || [])) {
			upsertProfile.run(
				p.name, p.company, p.currency, p.warehouse, p.selling_price_list,
				p.customer, p.write_off_account, p.write_off_cost_center,
				p.write_off_limit || 0, p.print_format, p.country,
				p.ignore_pricing_rule || 0, p.disable_rounded_total || 0,
				p.disabled || 0, p.taxes_and_charges, p.branch,
				JSON.stringify(p)
			)
		}
	})
	tx()

	// Pull POS Profile Users separately
	for (const p of (profiles || [])) {
		const users = await apiFetch(config, "frappe.client.get_list", {
			doctype: "POS Profile User",
			filters: { parent: p.name },
			fields: ["user"],
			limit_page_length: 0,
		})

		const userTx = db.transaction(() => {
			for (const u of (users || [])) {
				upsertUser.run(p.name, u.user)
			}
		})
		userTx()
	}

	// Pull POS Settings
	const posSettings = await apiFetch(config, "frappe.client.get_list", {
		doctype: "POS Settings",
		fields: ["*"],
		filters: { enabled: 1 },
		limit_page_length: 0,
	})

	const upsertSettings = db.prepare(`
		INSERT OR REPLACE INTO pos_settings (
			name, pos_profile, enabled, tax_inclusive,
			allow_user_to_edit_additional_discount, allow_user_to_edit_item_discount,
			allow_user_to_edit_rate, use_percentage_discount, max_discount_allowed,
			allow_credit_sale, allow_customer_credit_payment, allow_return,
			allow_partial_payment, use_exact_amount, decimal_precision,
			allow_negative_stock, enable_sales_persons, silent_print,
			allow_sales_order, allow_select_sales_order, create_only_sales_order,
			enable_session_lock, session_lock_timeout, show_variants_as_items
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`)

	const settingsTx = db.transaction(() => {
		for (const s of (posSettings || [])) {
			upsertSettings.run(
				s.name, s.pos_profile, s.enabled || 1, s.tax_inclusive || 0,
				s.allow_user_to_edit_additional_discount || 0, s.allow_user_to_edit_item_discount || 1,
				s.allow_user_to_edit_rate || 0, s.use_percentage_discount || 0, s.max_discount_allowed || 0,
				s.allow_credit_sale || 0, s.allow_customer_credit_payment || 0, s.allow_return || 0,
				s.allow_partial_payment || 0, s.use_exact_amount || 0, s.decimal_precision || "2",
				s.allow_negative_stock || 0, s.enable_sales_persons || "Disabled", s.silent_print || 0,
				s.allow_sales_order || 0, s.allow_select_sales_order || 0, s.create_only_sales_order || 0,
				s.enable_session_lock || 0, s.session_lock_timeout || 5, s.show_variants_as_items || 0
			)
		}
	})
	settingsTx()

	// Pull payment methods for each profile
	const upsertPaymentMethod = db.prepare(`
		INSERT OR REPLACE INTO pos_payment_methods (pos_profile, mode_of_payment, is_default, allow_in_returns, account)
		VALUES (?, ?, ?, ?, ?)
	`)

	for (const p of (profiles || [])) {
		const methods = await apiFetch(config, "frappe.client.get_list", {
			doctype: "POS Payment Method",
			filters: { parent: p.name },
			fields: ["mode_of_payment", "default", "allow_in_returns", "account"],
			limit_page_length: 0,
		})

		const methodTx = db.transaction(() => {
			for (const m of (methods || [])) {
				upsertPaymentMethod.run(p.name, m.mode_of_payment, m.default || 0, m.allow_in_returns || 0, m.account)
			}
		})
		methodTx()
	}
}

async function pullPaymentMethods(db, config, apiFetch) {
	const methods = await apiFetch(config, "frappe.client.get_list", {
		doctype: "Mode of Payment",
		fields: ["name", "type"],
		limit_page_length: 0,
	})

	const upsert = db.prepare(
		"INSERT OR REPLACE INTO payment_methods (mode_of_payment, type) VALUES (?, ?)"
	)

	const tx = db.transaction(() => {
		for (const m of (methods || [])) {
			upsert.run(m.name, m.type || "Cash")
		}
	})
	tx()
}

async function pullTaxTemplates(db, config, apiFetch) {
	const templates = await apiFetch(config, "frappe.client.get_list", {
		doctype: "Sales Taxes and Charges Template",
		fields: ["name", "title", "company", "is_default"],
		limit_page_length: 0,
	})

	const upsertTemplate = db.prepare(
		"INSERT OR REPLACE INTO tax_templates (name, title, company, is_default) VALUES (?, ?, ?, ?)"
	)

	const tx = db.transaction(() => {
		for (const t of (templates || [])) {
			upsertTemplate.run(t.name, t.title, t.company, t.is_default || 0)
		}
	})
	tx()

	// Pull tax rows for each template
	const upsertRow = db.prepare(`
		INSERT OR REPLACE INTO tax_rows (template_name, account_head, charge_type, rate, description, included_in_print_rate, idx)
		VALUES (?, ?, ?, ?, ?, ?, ?)
	`)

	for (const t of (templates || [])) {
		const rows = await apiFetch(config, "frappe.client.get_list", {
			doctype: "Sales Taxes and Charges",
			filters: { parent: t.name },
			fields: ["account_head", "charge_type", "rate", "description", "included_in_print_rate", "idx"],
			limit_page_length: 0,
		})

		const rowTx = db.transaction(() => {
			// Clear old rows for this template
			db.prepare("DELETE FROM tax_rows WHERE template_name = ?").run(t.name)
			for (const r of (rows || [])) {
				upsertRow.run(t.name, r.account_head, r.charge_type, r.rate || 0, r.description, r.included_in_print_rate || 0, r.idx || 0)
			}
		})
		rowTx()
	}
}

async function pullWarehouses(db, config, apiFetch) {
	const warehouses = await apiFetch(config, "frappe.client.get_list", {
		doctype: "Warehouse",
		fields: ["name", "warehouse_name", "company", "is_group", "parent_warehouse"],
		limit_page_length: 0,
	})

	const upsert = db.prepare(
		"INSERT OR REPLACE INTO warehouses (name, warehouse_name, company, is_group, parent_warehouse) VALUES (?, ?, ?, ?, ?)"
	)

	const tx = db.transaction(() => {
		for (const w of (warehouses || [])) {
			upsert.run(w.name, w.warehouse_name, w.company, w.is_group || 0, w.parent_warehouse)
		}
	})
	tx()
}

async function pullItemGroups(db, config, apiFetch) {
	const groups = await apiFetch(config, "frappe.client.get_list", {
		doctype: "Item Group",
		fields: ["name", "is_group", "parent_item_group", "lft", "rgt", "image"],
		limit_page_length: 0,
	})

	const upsert = db.prepare(
		"INSERT OR REPLACE INTO item_groups (name, is_group, parent_item_group, lft, rgt, image) VALUES (?, ?, ?, ?, ?, ?)"
	)

	const tx = db.transaction(() => {
		for (const g of (groups || [])) {
			upsert.run(g.name, g.is_group || 0, g.parent_item_group, g.lft, g.rgt, g.image)
		}
	})
	tx()
}

async function pullItems(db, config, apiFetch, onProgress, modifiedSince) {
	const batchSize = 500
	let start = 0
	let hasMore = true
	let totalPulled = 0

	const upsertItem = db.prepare(`
		INSERT OR REPLACE INTO items (
			item_code, item_name, description, stock_uom, image,
			is_stock_item, has_batch_no, has_serial_no, item_group,
			brand, has_variants, variant_of, custom_company, disabled,
			is_sales_item, synced_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`)

	const upsertBarcode = db.prepare(
		"INSERT OR IGNORE INTO item_barcodes (item_code, barcode, barcode_type) VALUES (?, ?, ?)"
	)

	while (hasMore) {
		const filters = { is_sales_item: 1 }
		if (modifiedSince) {
			filters.modified = [">", modifiedSince]
		}

		const items = await apiFetch(config, "frappe.client.get_list", {
			doctype: "Item",
			fields: [
				"name", "item_name", "description", "stock_uom", "image",
				"is_stock_item", "has_batch_no", "has_serial_no", "item_group",
				"brand", "has_variants", "variant_of", "custom_company", "disabled",
				"is_sales_item",
			],
			filters,
			limit_start: start,
			limit_page_length: batchSize,
			order_by: "name asc",
		})

		if (!items || items.length === 0) {
			hasMore = false
			break
		}

		const now = new Date().toISOString()

		const insertBatch = db.transaction(() => {
			for (const item of items) {
				upsertItem.run(
					item.name, item.item_name, item.description, item.stock_uom, item.image,
					item.is_stock_item || 0, item.has_batch_no || 0, item.has_serial_no || 0,
					item.item_group, item.brand, item.has_variants || 0, item.variant_of,
					item.custom_company, item.disabled || 0, item.is_sales_item || 1, now
				)
			}
		})
		insertBatch()

		// Pull barcodes for this batch
		const itemCodes = items.map(i => i.name)
		for (let bi = 0; bi < itemCodes.length; bi += 100) {
			const chunk = itemCodes.slice(bi, bi + 100)
			const barcodes = await apiFetch(config, "frappe.client.get_list", {
				doctype: "Item Barcode",
				filters: { parent: ["in", chunk] },
				fields: ["parent", "barcode", "barcode_type"],
				limit_page_length: 0,
			})

			const barcodeTx = db.transaction(() => {
				for (const b of (barcodes || [])) {
					upsertBarcode.run(b.parent, b.barcode, b.barcode_type)
				}
			})
			barcodeTx()
		}

		totalPulled += items.length
		start += batchSize

		if (onProgress) {
			onProgress({ current: totalPulled, total: totalPulled + batchSize, phase: `Downloaded ${totalPulled} items...` })
		}

		if (items.length < batchSize) hasMore = false

		// Small delay to avoid overwhelming ERPNext
		await new Promise(resolve => setTimeout(resolve, 200))
	}

	console.log(`[Sync] Pulled ${totalPulled} items`)
}

async function pullItemPrices(db, config, apiFetch, modifiedSince) {
	const batchSize = 1000
	let start = 0
	let hasMore = true

	const upsert = db.prepare(
		"INSERT OR REPLACE INTO item_prices (price_list, item_code, price_list_rate, currency, uom) VALUES (?, ?, ?, ?, ?)"
	)

	while (hasMore) {
		const filters = {}
		if (modifiedSince) filters.modified = [">", modifiedSince]

		const prices = await apiFetch(config, "frappe.client.get_list", {
			doctype: "Item Price",
			fields: ["price_list", "item_code", "price_list_rate", "currency", "uom"],
			filters,
			limit_start: start,
			limit_page_length: batchSize,
		})

		if (!prices || prices.length === 0) break

		const tx = db.transaction(() => {
			for (const p of prices) {
				upsert.run(p.price_list, p.item_code, p.price_list_rate || 0, p.currency, p.uom)
			}
		})
		tx()

		start += batchSize
		if (prices.length < batchSize) hasMore = false
	}
}

async function pullStock(db, config, apiFetch) {
	const batchSize = 1000
	let start = 0
	let hasMore = true

	const upsert = db.prepare(
		"INSERT OR REPLACE INTO stock (item_code, warehouse, actual_qty, synced_at) VALUES (?, ?, ?, ?)"
	)

	const now = new Date().toISOString()

	while (hasMore) {
		const bins = await apiFetch(config, "frappe.client.get_list", {
			doctype: "Bin",
			fields: ["item_code", "warehouse", "actual_qty"],
			limit_start: start,
			limit_page_length: batchSize,
		})

		if (!bins || bins.length === 0) break

		const tx = db.transaction(() => {
			for (const b of bins) {
				upsert.run(b.item_code, b.warehouse, b.actual_qty || 0, now)
			}
		})
		tx()

		start += batchSize
		if (bins.length < batchSize) hasMore = false
	}
}

async function pullCustomers(db, config, apiFetch, modifiedSince) {
	const batchSize = 500
	let start = 0
	let hasMore = true

	const upsert = db.prepare(`
		INSERT OR REPLACE INTO customers (
			name, customer_name, mobile_no, email_id,
			customer_group, territory, customer_type, loyalty_program,
			disabled, synced_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`)

	const now = new Date().toISOString()

	while (hasMore) {
		const filters = {}
		if (modifiedSince) filters.modified = [">", modifiedSince]

		const customers = await apiFetch(config, "frappe.client.get_list", {
			doctype: "Customer",
			fields: [
				"name", "customer_name", "mobile_no", "email_id",
				"customer_group", "territory", "customer_type", "loyalty_program", "disabled",
			],
			filters,
			limit_start: start,
			limit_page_length: batchSize,
		})

		if (!customers || customers.length === 0) break

		const tx = db.transaction(() => {
			for (const c of customers) {
				upsert.run(
					c.name, c.customer_name, c.mobile_no, c.email_id,
					c.customer_group, c.territory, c.customer_type, c.loyalty_program,
					c.disabled || 0, now
				)
			}
		})
		tx()

		start += batchSize
		if (customers.length < batchSize) hasMore = false
	}
}

async function pullSalesPersons(db, config, apiFetch) {
	const persons = await apiFetch(config, "frappe.client.get_list", {
		doctype: "Sales Person",
		fields: ["name", "sales_person_name", "commission_rate", "employee", "enabled"],
		filters: { enabled: 1 },
		limit_page_length: 0,
	})

	const upsert = db.prepare(
		"INSERT OR REPLACE INTO sales_persons (name, sales_person_name, commission_rate, employee, enabled) VALUES (?, ?, ?, ?, ?)"
	)

	const tx = db.transaction(() => {
		for (const sp of (persons || [])) {
			upsert.run(sp.name, sp.sales_person_name, sp.commission_rate || 0, sp.employee, sp.enabled || 1)
		}
	})
	tx()
}

async function pullUsers(db, config, apiFetch) {
	const users = await apiFetch(config, "frappe.client.get_list", {
		doctype: "User",
		fields: ["name", "full_name", "email", "language", "user_image", "enabled"],
		filters: { enabled: 1, user_type: "System User" },
		limit_page_length: 0,
	})

	const upsert = db.prepare(`
		INSERT OR REPLACE INTO users (name, full_name, email, language, user_image, is_active)
		VALUES (?, ?, ?, ?, ?, ?)
	`)

	const tx = db.transaction(() => {
		for (const u of (users || [])) {
			upsert.run(u.name, u.full_name, u.email, u.language || "en", u.user_image, u.enabled || 1)
		}
	})
	tx()
}

module.exports = { pullMasterData, pullDeltaUpdates }
