const { getDatabase } = require("../db/connection")

/**
 * Bootstrap API - replaces pos_next.api.bootstrap
 * Returns all data needed for POS app startup in a single call.
 */

async function getInitialData(_params, _req) {
	const db = getDatabase()

	const result = {
		success: true,
		site_name: "desktop.local",
		locale: _getUserLanguage(db),
		precision: _getPrecisionSettings(db),
		shift: null,
		pos_profile: null,
		pos_settings: null,
		payment_methods: [],
	}

	// Get current user
	const currentUser = db.prepare("SELECT value FROM settings WHERE key = 'current_user'").get()
	const user = currentUser?.value || "Administrator"

	// Find open shift for current user
	const shift = db.prepare(`
		SELECT name, pos_profile, period_start_date, status
		FROM pos_shifts
		WHERE user = ? AND status = 'Open' AND docstatus = 1
		ORDER BY period_start_date DESC
		LIMIT 1
	`).get(user)

	if (!shift) return result

	// Get POS Profile
	const profile = db.prepare("SELECT * FROM pos_profiles WHERE name = ?").get(shift.pos_profile)
	if (!profile) return result

	result.shift = {
		name: shift.name,
		pos_profile: shift.pos_profile,
		period_start_date: shift.period_start_date,
		status: shift.status,
	}

	result.pos_profile = {
		name: profile.name,
		company: profile.company,
		currency: profile.currency,
		warehouse: profile.warehouse,
		selling_price_list: profile.selling_price_list,
		customer: profile.customer,
		write_off_account: profile.write_off_account,
		write_off_cost_center: profile.write_off_cost_center,
		write_off_limit: profile.write_off_limit || 0,
		print_format: profile.print_format,
		auto_print: profile.auto_print || 0,
		country: profile.country,
		ignore_pricing_rule: profile.ignore_pricing_rule || 0,
	}

	result.pos_settings = _getPosSettings(db, profile)
	result.payment_methods = _getPaymentMethods(db, shift.pos_profile)

	return result
}

function _getUserLanguage(db) {
	const currentUser = db.prepare("SELECT value FROM settings WHERE key = 'current_user'").get()
	if (!currentUser) return "en"

	const user = db.prepare("SELECT language FROM users WHERE name = ?").get(currentUser.value)
	return (user?.language || "en").toLowerCase()
}

function _getPrecisionSettings(db) {
	const getSetting = (key, defaultVal) => {
		const row = db.prepare("SELECT value FROM system_settings WHERE key = ?").get(key)
		return row ? row.value : defaultVal
	}

	return {
		currency: parseInt(getSetting("currency_precision", "2"), 10),
		float: parseInt(getSetting("float_precision", "3"), 10),
		rounding_method: getSetting("rounding_method", "Commercial Rounding"),
		number_format: getSetting("number_format", "#,###.##"),
	}
}

function _getPosSettings(db, profile) {
	const settings = db.prepare(
		"SELECT * FROM pos_settings WHERE pos_profile = ? AND enabled = 1"
	).get(profile.name)

	const defaults = {
		enabled: 0,
		tax_inclusive: 0,
		allow_user_to_edit_additional_discount: 0,
		allow_user_to_edit_item_discount: 1,
		allow_user_to_edit_rate: 0,
		use_percentage_discount: 0,
		max_discount_allowed: 0,
		disable_rounded_total: 0,
		allow_credit_sale: 0,
		allow_customer_credit_payment: 0,
		allow_return: 0,
		allow_write_off_change: 0,
		allow_partial_payment: 0,
		use_exact_amount: 0,
		decimal_precision: "2",
		allow_negative_stock: 0,
		enable_sales_persons: "Disabled",
		silent_print: 0,
		allow_sales_order: 0,
		allow_select_sales_order: 0,
		create_only_sales_order: 0,
		enable_session_lock: 0,
		session_lock_timeout: 5,
		show_variants_as_items: 0,
	}

	const result = settings || defaults

	// Derived from POS Profile (single source of truth)
	result.allow_write_off_change =
		profile.write_off_account && (profile.write_off_limit || 0) > 0 ? 1 : 0
	result.disable_rounded_total = profile.disable_rounded_total || 0

	return result
}

function _getPaymentMethods(db, posProfileName) {
	return db.prepare(`
		SELECT
			ppm.mode_of_payment,
			ppm.is_default as "default",
			ppm.allow_in_returns,
			COALESCE(pm.type, 'Cash') as type
		FROM pos_payment_methods ppm
		LEFT JOIN payment_methods pm ON ppm.mode_of_payment = pm.mode_of_payment
		WHERE ppm.pos_profile = ?
		ORDER BY ppm.id
	`).all(posProfileName)
}

module.exports = { getInitialData }
