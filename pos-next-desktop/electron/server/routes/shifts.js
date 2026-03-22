const { getDatabase } = require("../db/connection")
const { FrappeError } = require("../frappe-compat")

/**
 * Shifts API - replaces pos_next.api.shifts
 * Local shift management in SQLite.
 */

function _getCurrentUser(db) {
	const row = db.prepare("SELECT value FROM settings WHERE key = 'current_user'").get()
	return row?.value || "Administrator"
}

async function getOpeningDialogData() {
	const db = getDatabase()
	const user = _getCurrentUser(db)

	// Get POS Profiles where current user is assigned
	const profiles = db.prepare(`
		SELECT DISTINCT p.name, p.company, p.currency, p.warehouse, p.selling_price_list
		FROM pos_profiles p
		INNER JOIN pos_profile_users pu ON pu.pos_profile = p.name
		WHERE p.disabled = 0 AND pu.user = ?
		ORDER BY p.name
	`).all(user)

	// Derive companies
	const companyNames = [...new Set(profiles.map(p => p.company).filter(Boolean))]
	const companies = companyNames.map(name => ({ name }))

	// Get payment methods for these profiles
	const profileNames = profiles.map(p => p.name)
	let paymentMethods = []

	if (profileNames.length) {
		const placeholders = profileNames.map(() => "?").join(",")
		paymentMethods = db.prepare(`
			SELECT ppm.*, p.currency
			FROM pos_payment_methods ppm
			LEFT JOIN pos_profiles p ON ppm.pos_profile = p.name
			WHERE ppm.pos_profile IN (${placeholders})
			ORDER BY ppm.pos_profile
		`).all(...profileNames)
	}

	return {
		pos_profiles_data: profiles,
		companies,
		payments_method: paymentMethods,
	}
}

async function checkOpeningShift(params) {
	const db = getDatabase()
	const user = params?.user || _getCurrentUser(db)

	const shift = db.prepare(`
		SELECT name, pos_profile, period_start_date
		FROM pos_shifts
		WHERE user = ? AND status = 'Open' AND docstatus = 1
		ORDER BY period_start_date DESC
		LIMIT 1
	`).get(user)

	if (!shift) return null

	const profile = db.prepare("SELECT * FROM pos_profiles WHERE name = ?").get(shift.pos_profile)
	const company = db.prepare("SELECT * FROM companies WHERE name = ?").get(profile?.company)

	return {
		pos_opening_shift: {
			name: shift.name,
			user,
			pos_profile: shift.pos_profile,
			period_start_date: shift.period_start_date,
			status: "Open",
			docstatus: 1,
			balance_details: db.prepare(
				"SELECT mode_of_payment, amount FROM pos_shift_details WHERE shift_name = ? AND detail_type = 'opening'"
			).all(shift.name),
		},
		pos_profile: profile,
		company,
		server_now: new Date().toISOString(),
	}
}

async function createOpeningShift(params) {
	const db = getDatabase()
	const { pos_profile, company, balance_details } = params
	const user = _getCurrentUser(db)

	// Check if already has an open shift
	const existing = await checkOpeningShift({ user })
	if (existing) {
		throw new FrappeError(`You already have an open shift: ${existing.pos_opening_shift.name}`)
	}

	const balanceData = typeof balance_details === "string" ? JSON.parse(balance_details) : balance_details
	const now = new Date()
	const shiftName = `POS-SHIFT-${now.getTime()}`

	const createShift = db.transaction(() => {
		db.prepare(`
			INSERT INTO pos_shifts (name, user, pos_profile, company, status,
				period_start_date, posting_date, posting_time, docstatus)
			VALUES (?, ?, ?, ?, 'Open', ?, ?, ?, 1)
		`).run(
			shiftName, user, pos_profile, company,
			now.toISOString(),
			now.toISOString().split("T")[0],
			now.toTimeString().split(" ")[0]
		)

		// Insert balance details
		const insertDetail = db.prepare(`
			INSERT INTO pos_shift_details (shift_name, mode_of_payment, amount, detail_type)
			VALUES (?, ?, ?, 'opening')
		`)
		for (const detail of (balanceData || [])) {
			insertDetail.run(shiftName, detail.mode_of_payment, detail.opening_amount || detail.amount || 0)
		}
	})

	createShift()

	const profile = db.prepare("SELECT * FROM pos_profiles WHERE name = ?").get(pos_profile)
	const companyDoc = db.prepare("SELECT * FROM companies WHERE name = ?").get(company)

	return {
		pos_opening_shift: {
			name: shiftName,
			user,
			pos_profile,
			company,
			period_start_date: now.toISOString(),
			status: "Open",
			docstatus: 1,
			balance_details: balanceData,
		},
		pos_profile: profile,
		company: companyDoc,
	}
}

async function getClosingShiftData(params) {
	const db = getDatabase()
	const { opening_shift } = params

	const shift = db.prepare("SELECT * FROM pos_shifts WHERE name = ?").get(opening_shift)
	if (!shift) throw new FrappeError("Opening shift not found")

	// Get all invoices for this shift
	const invoices = db.prepare(`
		SELECT * FROM invoices
		WHERE pos_opening_shift = ? AND docstatus = 1
	`).all(opening_shift)

	// Calculate payment totals by mode
	const paymentTotals = {}
	for (const inv of invoices) {
		const payments = db.prepare(
			"SELECT mode_of_payment, amount FROM invoice_payments WHERE invoice_name = ?"
		).all(inv.name)

		for (const p of payments) {
			if (!paymentTotals[p.mode_of_payment]) paymentTotals[p.mode_of_payment] = 0
			paymentTotals[p.mode_of_payment] += p.amount
		}
	}

	// Get opening balances
	const openingDetails = db.prepare(
		"SELECT mode_of_payment, amount FROM pos_shift_details WHERE shift_name = ? AND detail_type = 'opening'"
	).all(opening_shift)

	// Build payment reconciliation
	const paymentReconciliation = []
	const allModes = new Set([
		...Object.keys(paymentTotals),
		...openingDetails.map(d => d.mode_of_payment),
	])

	for (const mode of allModes) {
		const opening = openingDetails.find(d => d.mode_of_payment === mode)?.amount || 0
		const collected = paymentTotals[mode] || 0
		paymentReconciliation.push({
			mode_of_payment: mode,
			opening_amount: opening,
			expected_amount: opening + collected,
			closing_amount: opening + collected, // Default to expected
			difference: 0,
		})
	}

	return {
		opening_shift: shift,
		invoices,
		total_invoices: invoices.length,
		grand_total: invoices.reduce((sum, inv) => sum + (inv.grand_total || 0), 0),
		net_total: invoices.reduce((sum, inv) => sum + (inv.net_total || 0), 0),
		total_quantity: 0,
		payment_reconciliation: paymentReconciliation,
	}
}

async function submitClosingShift(params) {
	const db = getDatabase()
	const { closing_shift } = params
	const data = typeof closing_shift === "string" ? JSON.parse(closing_shift) : closing_shift

	const openingShiftName = data.pos_opening_shift || data.opening_shift?.name
	if (!openingShiftName) throw new FrappeError("Opening shift reference required")

	const closingName = `POS-CLOSE-${Date.now()}`

	const closeShift = db.transaction(() => {
		// Update opening shift to closed
		db.prepare(`
			UPDATE pos_shifts SET status = 'Closed', closing_shift = ?
			WHERE name = ?
		`).run(closingName, openingShiftName)

		// Insert closing balance details
		const insertDetail = db.prepare(`
			INSERT INTO pos_shift_details (shift_name, mode_of_payment, amount, detail_type)
			VALUES (?, ?, ?, 'closing')
		`)

		for (const detail of (data.payment_reconciliation || [])) {
			insertDetail.run(openingShiftName, detail.mode_of_payment, detail.closing_amount || 0)
		}
	})

	closeShift()

	return { name: closingName, status: "success" }
}

module.exports = {
	getOpeningDialogData,
	checkOpeningShift,
	createOpeningShift,
	getClosingShiftData,
	submitClosingShift,
}
