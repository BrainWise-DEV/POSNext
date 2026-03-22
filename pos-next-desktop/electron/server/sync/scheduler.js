const { triggerSync, checkConnection } = require("./engine")

/**
 * Sync Scheduler - Runs periodic sync when online.
 * Default interval: 5 minutes.
 */

let intervalId = null
const SYNC_INTERVAL_MS = 5 * 60 * 1000 // 5 minutes

/**
 * Start the periodic sync scheduler.
 */
function startScheduler(intervalMs = SYNC_INTERVAL_MS) {
	if (intervalId) {
		console.log("[Scheduler] Already running")
		return
	}

	console.log(`[Scheduler] Starting sync every ${intervalMs / 1000}s`)

	intervalId = setInterval(async () => {
		try {
			const { connected } = await checkConnection()
			if (connected) {
				console.log("[Scheduler] Online - triggering sync...")
				await triggerSync()
			} else {
				console.log("[Scheduler] Offline - skipping sync")
			}
		} catch (error) {
			console.error("[Scheduler] Sync error:", error.message)
		}
	}, intervalMs)

	// Also run an initial sync check after a short delay
	setTimeout(async () => {
		try {
			const { connected } = await checkConnection()
			if (connected) {
				console.log("[Scheduler] Initial sync on startup...")
				await triggerSync()
			}
		} catch {
			// Silently skip initial sync if offline
		}
	}, 10000) // 10 seconds after startup
}

/**
 * Stop the periodic sync scheduler.
 */
function stopScheduler() {
	if (intervalId) {
		clearInterval(intervalId)
		intervalId = null
		console.log("[Scheduler] Stopped")
	}
}

module.exports = { startScheduler, stopScheduler }
