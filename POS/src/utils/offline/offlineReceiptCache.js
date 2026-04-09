import { logger } from "@/utils/logger"

const log = logger.create("OfflineReceiptCache")
const KEY_PREFIX = "pos_next_offline_rcpt:"

/**
 * Persist a full receipt payload for a synthetic offline invoice id (e.g.
 * pos_offline_<uuid>). Used so print / detail views never call ERPNext for
 * names that are not in the DB yet.
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

/**
 * Drop a single cached receipt — called after the invoice has been synced
 * to the server and the server name is available for future lookups.
 */
export function removeOfflineReceiptPayload(name) {
	if (typeof sessionStorage === "undefined" || !name) return
	try {
		sessionStorage.removeItem(`${KEY_PREFIX}${name}`)
	} catch (e) {
		log.warn("Could not remove offline receipt:", e)
	}
}

/**
 * Remove all cached offline receipts. Called on logout / session cleanup to
 * prevent cross-cashier leakage on shared terminals.
 */
export function clearAllOfflineReceiptPayloads() {
	if (typeof sessionStorage === "undefined") return
	try {
		const keys = []
		for (let i = 0; i < sessionStorage.length; i++) {
			const key = sessionStorage.key(i)
			if (key?.startsWith(KEY_PREFIX)) keys.push(key)
		}
		for (const key of keys) sessionStorage.removeItem(key)
	} catch (e) {
		log.warn("Could not clear offline receipts:", e)
	}
}
