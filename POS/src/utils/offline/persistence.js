/**
 * @fileoverview Browser persistent-storage permission.
 *
 * `navigator.storage.persist()` asks the browser to mark this origin's
 * storage (IndexedDB included) as **persistent** — the browser then
 * promises not to evict the data under storage pressure. It is granted
 * automatically on most browsers when the site is "installed" (PWA),
 * has notification permission, or has a high site-engagement score.
 *
 * This is the cheapest durability win. It does NOT defend against
 * "Clear site data" or browser reinstall — for that, see diskBackup.js
 * (QZ-Tray on-disk mirror).
 *
 * Idempotent: safe to call repeatedly. Caches the result in a setting
 * so we don't spam the API on every boot.
 *
 * @module utils/offline/persistence
 */

import { logger } from "../logger"
import { getSetting, setSetting } from "./db"

const log = logger.create("Persistence")

const PERSISTED_KEY = "storage_persisted_at"

/**
 * Snapshot of the current persistent-storage state for the UI to display.
 * @typedef {Object} PersistenceStatus
 * @property {boolean} supported - Browser exposes `navigator.storage.persist`
 * @property {boolean} persisted - Storage is currently marked persistent
 * @property {?number} quota - Estimated bytes available, or null if unknown
 * @property {?number} usage - Estimated bytes used, or null if unknown
 */

/**
 * Check the current persistence state without prompting.
 * @returns {Promise<PersistenceStatus>}
 */
export async function getPersistenceStatus() {
	const supported =
		typeof navigator !== "undefined" &&
		!!navigator.storage &&
		typeof navigator.storage.persist === "function"

	if (!supported) {
		return { supported: false, persisted: false, quota: null, usage: null }
	}

	let persisted = false
	try {
		persisted = await navigator.storage.persisted()
	} catch (error) {
		log.warn("navigator.storage.persisted() threw", error)
	}

	let quota = null
	let usage = null
	try {
		if (typeof navigator.storage.estimate === "function") {
			const estimate = await navigator.storage.estimate()
			quota = estimate?.quota ?? null
			usage = estimate?.usage ?? null
		}
	} catch (error) {
		log.warn("navigator.storage.estimate() threw", error)
	}

	return { supported, persisted, quota, usage }
}

/**
 * Request persistent storage. The browser may prompt the user, grant
 * silently, or refuse — all are surfaced in the return value.
 *
 * @returns {Promise<PersistenceStatus>}
 */
export async function requestPersistentStorage() {
	const initial = await getPersistenceStatus()
	if (!initial.supported) {
		log.info("Persistent storage API not supported in this browser")
		return initial
	}
	if (initial.persisted) {
		// Already persistent — nothing to do.
		return initial
	}

	try {
		const granted = await navigator.storage.persist()
		log.info(
			granted
				? "Persistent storage granted by browser"
				: "Persistent storage NOT granted (data may be evicted under pressure)",
		)
		if (granted) {
			await setSetting(PERSISTED_KEY, Date.now())
		}
	} catch (error) {
		log.warn("navigator.storage.persist() threw", error)
	}

	return await getPersistenceStatus()
}

/**
 * Boot-time helper: call `requestPersistentStorage` once and remember
 * the result so subsequent boots don't re-prompt unless the grant was
 * lost. Best-effort — never throws.
 *
 * @returns {Promise<PersistenceStatus>}
 */
export async function ensurePersistentStorage() {
	try {
		const lastPersistedAt = await getSetting(PERSISTED_KEY, null)
		const status = await getPersistenceStatus()

		if (status.persisted) {
			// Refresh the marker so we know it's still good.
			if (!lastPersistedAt) await setSetting(PERSISTED_KEY, Date.now())
			return status
		}

		// Either never granted, or grant was revoked — try once.
		return await requestPersistentStorage()
	} catch (error) {
		log.warn("ensurePersistentStorage failed", error)
		return {
			supported: false,
			persisted: false,
			quota: null,
			usage: null,
		}
	}
}
