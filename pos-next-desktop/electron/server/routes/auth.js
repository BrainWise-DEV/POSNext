const { getDatabase } = require("../db/connection")

/**
 * Auth API - replaces pos_next.api.auth
 * Local authentication against SQLite users table.
 */

async function verifySessionPassword(params) {
	const db = getDatabase()
	const { password } = params

	const currentUser = db.prepare("SELECT value FROM settings WHERE key = 'current_user'").get()
	if (!currentUser) return { verified: false }

	const user = db.prepare("SELECT password_hash FROM users WHERE name = ?").get(currentUser.value)
	if (!user) return { verified: false }

	// Simple comparison (in production, use bcrypt)
	const verified = user.password_hash === password
	return { verified }
}

module.exports = { verifySessionPassword }
