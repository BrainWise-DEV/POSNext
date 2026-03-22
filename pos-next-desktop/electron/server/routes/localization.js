const { getDatabase } = require("../db/connection")

/**
 * Localization API - replaces pos_next.api.localization
 * Local translation support from SQLite cache.
 */

async function getAppTranslations(params) {
	const db = getDatabase()
	const { locale } = params

	const row = db.prepare("SELECT data_json FROM translations WHERE locale = ?").get(locale || "en")
	if (!row?.data_json) return {}

	try {
		return JSON.parse(row.data_json)
	} catch {
		return {}
	}
}

async function getUserLanguage() {
	const db = getDatabase()
	const user = db.prepare("SELECT value FROM settings WHERE key = 'current_user'").get()
	if (!user) return "en"

	const userDoc = db.prepare("SELECT language FROM users WHERE name = ?").get(user.value)
	return (userDoc?.language || "en").toLowerCase()
}

async function getAllowedLocales() {
	const db = getDatabase()
	const locales = db.prepare("SELECT locale FROM translations").all()
	return locales.map(l => l.locale)
}

async function changeUserLanguage(params) {
	const db = getDatabase()
	const { language } = params

	const user = db.prepare("SELECT value FROM settings WHERE key = 'current_user'").get()
	if (user) {
		db.prepare("UPDATE users SET language = ? WHERE name = ?").run(language, user.value)
	}

	return { success: true }
}

module.exports = { getAppTranslations, getUserLanguage, getAllowedLocales, changeUserLanguage }
