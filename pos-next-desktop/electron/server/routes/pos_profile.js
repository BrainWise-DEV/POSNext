const { getDatabase } = require("../db/connection")
const { FrappeError } = require("../frappe-compat")

/**
 * POS Profile API - replaces pos_next.api.pos_profile
 */

async function getPosProfiles() {
	const db = getDatabase()
	const user = db.prepare("SELECT value FROM settings WHERE key = 'current_user'").get()?.value

	return db.prepare(`
		SELECT DISTINCT p.*
		FROM pos_profiles p
		INNER JOIN pos_profile_users pu ON pu.pos_profile = p.name
		WHERE p.disabled = 0 AND pu.user = ?
		ORDER BY p.name
	`).all(user || "Administrator")
}

async function getPosProfileData(params) {
	const db = getDatabase()
	const { pos_profile } = params

	const profile = db.prepare("SELECT * FROM pos_profiles WHERE name = ?").get(pos_profile)
	if (!profile) throw new FrappeError(`POS Profile ${pos_profile} not found`)

	const settings = db.prepare(
		"SELECT * FROM pos_settings WHERE pos_profile = ? AND enabled = 1"
	).get(pos_profile) || {}

	const paymentMethods = db.prepare(`
		SELECT ppm.mode_of_payment, ppm.is_default as "default", ppm.allow_in_returns,
			   COALESCE(pm.type, 'Cash') as type
		FROM pos_payment_methods ppm
		LEFT JOIN payment_methods pm ON ppm.mode_of_payment = pm.mode_of_payment
		WHERE ppm.pos_profile = ?
	`).all(pos_profile)

	// Item groups hierarchy
	const itemGroups = db.prepare("SELECT * FROM item_groups ORDER BY lft").all()

	return {
		pos_profile: profile,
		pos_settings: settings,
		payment_methods: paymentMethods,
		item_groups_hierarchy: itemGroups,
	}
}

async function getPosSettings(params) {
	const db = getDatabase()
	const { pos_profile } = params

	return db.prepare(
		"SELECT * FROM pos_settings WHERE pos_profile = ? AND enabled = 1"
	).get(pos_profile) || {}
}

async function getPaymentMethods(params) {
	const db = getDatabase()
	const { pos_profile } = params

	return db.prepare(`
		SELECT ppm.mode_of_payment, ppm.is_default as "default", ppm.allow_in_returns,
			   COALESCE(pm.type, 'Cash') as type, ppm.account
		FROM pos_payment_methods ppm
		LEFT JOIN payment_methods pm ON ppm.mode_of_payment = pm.mode_of_payment
		WHERE ppm.pos_profile = ?
		ORDER BY ppm.id
	`).all(pos_profile)
}

async function getTaxes(params) {
	const db = getDatabase()
	const { pos_profile } = params

	const profile = db.prepare("SELECT taxes_and_charges FROM pos_profiles WHERE name = ?").get(pos_profile)
	if (!profile?.taxes_and_charges) return []

	return db.prepare(
		"SELECT * FROM tax_rows WHERE template_name = ? ORDER BY idx"
	).all(profile.taxes_and_charges)
}

async function getWarehouses(params) {
	const db = getDatabase()
	const { company } = params

	let query = "SELECT * FROM warehouses WHERE is_group = 0"
	const queryParams = []

	if (company) {
		query += " AND company = ?"
		queryParams.push(company)
	}

	return db.prepare(query).all(...queryParams)
}

async function getDefaultCustomer(params) {
	const db = getDatabase()
	const { pos_profile } = params

	const profile = db.prepare("SELECT customer FROM pos_profiles WHERE name = ?").get(pos_profile)
	if (!profile?.customer) return null

	return db.prepare("SELECT * FROM customers WHERE name = ?").get(profile.customer)
}

async function updateWarehouse(params) {
	const db = getDatabase()
	const { pos_profile, warehouse } = params

	db.prepare("UPDATE pos_profiles SET warehouse = ? WHERE name = ?").run(warehouse, pos_profile)
	return { success: true }
}

async function getWalletPaymentFlags() {
	return { has_wallet_payment: false, wallet_modes: [] }
}

async function getSalesPersons(params) {
	const db = getDatabase()
	return db.prepare("SELECT * FROM sales_persons WHERE enabled = 1 ORDER BY name").all()
}

// Admin operations - these require online connectivity in production
async function getCreatePosProfile() {
	throw new FrappeError("POS Profile creation requires internet connection", { httpStatus: 503 })
}

async function createPosProfile() {
	throw new FrappeError("POS Profile creation requires internet connection", { httpStatus: 503 })
}

async function updatePosProfile() {
	throw new FrappeError("POS Profile update requires internet connection", { httpStatus: 503 })
}

async function deletePosProfile() {
	throw new FrappeError("POS Profile deletion requires internet connection", { httpStatus: 503 })
}

module.exports = {
	getPosProfiles,
	getPosProfileData,
	getPosSettings,
	getPaymentMethods,
	getTaxes,
	getWarehouses,
	getDefaultCustomer,
	updateWarehouse,
	getWalletPaymentFlags,
	getSalesPersons,
	getCreatePosProfile,
	createPosProfile,
	updatePosProfile,
	deletePosProfile,
}
