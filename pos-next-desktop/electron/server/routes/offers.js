const { getDatabase } = require("../db/connection")

/**
 * Offers API - replaces pos_next.api.offers
 * Simplified local pricing rules engine.
 */

async function getOffers(params) {
	const db = getDatabase()
	const { pos_profile } = params

	const today = new Date().toISOString().split("T")[0]

	let query = "SELECT * FROM offers WHERE disabled = 0"
	const queryParams = []

	if (pos_profile) {
		query += " AND (pos_profile = ? OR pos_profile IS NULL)"
		queryParams.push(pos_profile)
	}

	query += " AND (valid_from IS NULL OR valid_from <= ?)"
	query += " AND (valid_upto IS NULL OR valid_upto >= ?)"
	queryParams.push(today, today)

	const offers = db.prepare(query).all(...queryParams)

	// Parse data_json for full offer details
	return offers.map(o => {
		if (o.data_json) {
			try { return { ...o, ...JSON.parse(o.data_json) } } catch { /* ignore */ }
		}
		return o
	})
}

async function getActiveCoupons(params) {
	const db = getDatabase()
	const today = new Date().toISOString().split("T")[0]

	return db.prepare(`
		SELECT * FROM coupons
		WHERE (valid_from IS NULL OR valid_from <= ?)
		AND (valid_upto IS NULL OR valid_upto >= ?)
		AND (maximum_use = 0 OR used < maximum_use)
	`).all(today, today)
}

async function validateCoupon(params) {
	const db = getDatabase()
	const { coupon_code } = params

	const coupon = db.prepare("SELECT * FROM coupons WHERE coupon_code = ?").get(coupon_code)
	if (!coupon) return { valid: false, message: "Invalid coupon code" }

	const today = new Date().toISOString().split("T")[0]
	if (coupon.valid_upto && coupon.valid_upto < today) {
		return { valid: false, message: "Coupon has expired" }
	}
	if (coupon.maximum_use > 0 && coupon.used >= coupon.maximum_use) {
		return { valid: false, message: "Coupon usage limit reached" }
	}

	return { valid: true, coupon }
}

module.exports = { getOffers, getActiveCoupons, validateCoupon }
