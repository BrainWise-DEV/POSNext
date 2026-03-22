const { getDatabase } = require("../db/connection")
const { pullMasterData, pullDeltaUpdates } = require("./pull")
const { pushInvoices, pushCustomers, pushShifts } = require("./push")

/**
 * Bidirectional Sync Engine
 *
 * Coordinates data synchronization between local SQLite and remote ERPNext.
 * - Pull: Download master data (items, customers, stock, etc.) from ERPNext
 * - Push: Upload invoices, new customers, and shift data to ERPNext
 */

let syncState = {
	status: "idle", // idle, syncing, error, offline
	lastSync: null,
	lastError: null,
	progress: { current: 0, total: 0, phase: "" },
}

/**
 * Get the current sync status.
 */
function getSyncStatus() {
	return { ...syncState }
}

/**
 * Get ERPNext connection config from settings.
 */
function getERPNextConfig() {
	const db = getDatabase()
	const getSetting = (key) => {
		const row = db.prepare("SELECT value FROM settings WHERE key = ?").get(key)
		return row?.value || ""
	}

	return {
		url: getSetting("erpnext_url"),
		apiKey: getSetting("api_key"),
		apiSecret: getSetting("api_secret"),
	}
}

/**
 * Check if ERPNext connection is configured and reachable.
 */
async function checkConnection() {
	const config = getERPNextConfig()
	if (!config.url || !config.apiKey || !config.apiSecret) {
		return { connected: false, reason: "Not configured" }
	}

	try {
		const response = await fetchFromERPNext(config, "frappe.auth.get_logged_user", {})
		return { connected: true, user: response }
	} catch (error) {
		return { connected: false, reason: error.message }
	}
}

/**
 * Make an authenticated API call to ERPNext.
 */
async function fetchFromERPNext(config, method, params = {}) {
	const url = `${config.url}/api/method/${method}`

	const response = await fetch(url, {
		method: "POST",
		headers: {
			"Content-Type": "application/json",
			Authorization: `token ${config.apiKey}:${config.apiSecret}`,
		},
		body: JSON.stringify(params),
	})

	if (!response.ok) {
		const text = await response.text()
		throw new Error(`ERPNext API error (${response.status}): ${text.slice(0, 200)}`)
	}

	const data = await response.json()
	return data.message
}

/**
 * Trigger a full sync cycle (pull + push).
 */
async function triggerSync() {
	if (syncState.status === "syncing") {
		return { success: false, message: "Sync already in progress" }
	}

	const config = getERPNextConfig()
	if (!config.url) {
		return { success: false, message: "ERPNext not configured" }
	}

	syncState.status = "syncing"
	syncState.lastError = null

	try {
		// Phase 1: Push local changes to server
		syncState.progress = { current: 0, total: 3, phase: "Pushing invoices..." }
		await pushInvoices(config, fetchFromERPNext)

		syncState.progress = { current: 1, total: 3, phase: "Pushing customers..." }
		await pushCustomers(config, fetchFromERPNext)

		syncState.progress = { current: 2, total: 3, phase: "Pushing shifts..." }
		await pushShifts(config, fetchFromERPNext)

		// Phase 2: Pull updates from server
		syncState.progress = { current: 0, total: 1, phase: "Pulling updates..." }
		await pullDeltaUpdates(config, fetchFromERPNext, (progress) => {
			syncState.progress = progress
		})

		// Update last sync time
		const db = getDatabase()
		const now = new Date().toISOString()
		db.prepare("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_sync', ?)").run(now)

		syncState.status = "idle"
		syncState.lastSync = now
		syncState.progress = { current: 0, total: 0, phase: "" }

		return { success: true, lastSync: now }
	} catch (error) {
		syncState.status = "error"
		syncState.lastError = error.message
		console.error("[Sync] Error:", error)
		return { success: false, message: error.message }
	}
}

/**
 * Run initial data provisioning (first-time setup).
 * Downloads all master data from ERPNext.
 */
async function initialProvision(config, onProgress) {
	syncState.status = "syncing"

	try {
		await pullMasterData(config, fetchFromERPNext, (progress) => {
			syncState.progress = progress
			if (onProgress) onProgress(progress)
		})

		const db = getDatabase()
		const now = new Date().toISOString()
		db.prepare("INSERT OR REPLACE INTO settings (key, value) VALUES ('setup_complete', '1')").run()
		db.prepare("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_sync', ?)").run(now)

		syncState.status = "idle"
		syncState.lastSync = now
		return { success: true }
	} catch (error) {
		syncState.status = "error"
		syncState.lastError = error.message
		throw error
	}
}

module.exports = {
	getSyncStatus,
	checkConnection,
	triggerSync,
	initialProvision,
	fetchFromERPNext,
	getERPNextConfig,
}
