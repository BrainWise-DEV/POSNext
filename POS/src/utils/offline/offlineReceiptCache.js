import { logger } from "@/utils/logger"

const log = logger.create("OfflineReceiptCache")
const KEY_PREFIX = "pos_next_offline_rcpt:"

/**
 * Persist a full receipt payload for a synthetic offline invoice id (e.g. OFFLINE-…).
 * Used so print / detail views never call ERPNext for names that are not in the DB yet.
 */
export function cacheOfflineReceiptPayload(name, doc) {
	if (typeof sessionStorage === "undefined" || !name || !doc) return
	try {
		sessionStorage.setItem(`${KEY_PREFIX}${name}`, JSON.stringify(doc))
	} catch (e) {
		log.warn("Could not cache offline receipt:", e)
	}
}

export function getOfflineReceiptPayload(name) {
	if (typeof sessionStorage === "undefined" || !name) return null
	try {
		const raw = sessionStorage.getItem(`${KEY_PREFIX}${name}`)
		return raw ? JSON.parse(raw) : null
	} catch {
		return null
	}
}
