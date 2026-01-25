import { call } from "@/utils/apiWrapper"
import { logger } from "@/utils/logger"
import { CoalescingMutex } from "@/utils/mutex"
import { db } from "./db"
import { offlineState } from "./offlineState"
import { generateOfflineId } from "./uuid"

// Re-export for backwards compatibility
export { generateOfflineId }

// Create namespaced logger for sync operations
const log = logger.create("Sync")

// Mutex for sync operations
const syncMutex = new CoalescingMutex({ timeout: 60000, name: "InvoiceSync" })

// ============================================================================
// CONSTANTS
// ============================================================================

const SYNC_CONFIG = {
	MAX_RETRY_COUNT: 3,
	CLEANUP_AGE_DAYS: 7,
	PING_TIMEOUT_MS: 3000,
}

// Duplicate error patterns to detect already-synced invoices
const DUPLICATE_ERROR_PATTERNS = [
	"DUPLICATE_OFFLINE_INVOICE",
	"already been synced",
]

// Temporary error patterns that should trigger a retry after delay
const SYNC_IN_PROGRESS_PATTERNS = [
	"SYNC_IN_PROGRESS",
	"currently being processed",
]

// ============================================================================
// SERVER CONNECTIVITY
// ============================================================================

/**
 * Ping server to check connectivity
 * @returns {Promise<boolean>} Whether server is reachable
 */
export const pingServer = async () => {
	if (typeof window === "undefined") return true

	try {
		const controller = new AbortController()
		const timeoutId = setTimeout(() => controller.abort(), SYNC_CONFIG.PING_TIMEOUT_MS)

		const response = await fetch("/api/method/pos_next.api.ping", {
			method: "GET",
			signal: controller.signal,
		})

		clearTimeout(timeoutId)
		const isOnline = response.ok
		// Update centralized state (handles window sync automatically)
		offlineState.setServerOnline(isOnline)
		return isOnline
	} catch (error) {
		// Server unreachable
		offlineState.setServerOnline(false)
		return false
	}
}

/**
 * Check if currently offline
 * @returns {boolean}
 */
export const isOffline = () => {
	if (typeof window === "undefined") return false
	return offlineState.isOffline
}

// ============================================================================
// OFFLINE INVOICE QUEUE OPERATIONS
// ============================================================================

/**
 * Save invoice to offline queue with unique offline_id for deduplication
 * @param {Object} invoiceData - Invoice data to save
 * @returns {Promise<{success: boolean, id: number, offline_id: string}>}
 */
export const saveOfflineInvoice = async (invoiceData) => {
	if (!invoiceData.items?.length) {
		throw new Error("Cannot save empty invoice")
	}

	// Clean data (remove reactive properties) and add offline_id
	const cleanData = JSON.parse(JSON.stringify(invoiceData))
	const offlineId = generateOfflineId()
	cleanData.offline_id = offlineId

	const id = await db.invoice_queue.add({
		offline_id: offlineId,
		data: cleanData,
		timestamp: Date.now(),
		synced: false,
		retry_count: 0,
	})

	await updateLocalStock(cleanData.items)

	log.info(`Invoice saved to offline queue`, { offline_id: offlineId })
	return { success: true, id, offline_id: offlineId }
}

/**
 * Get all pending (unsynced) offline invoices
 * @returns {Promise<Array>}
 */
export const getOfflineInvoices = async () => {
	try {
		return await db.invoice_queue.filter((inv) => !inv.synced).toArray()
	} catch (error) {
		log.error("Failed to get offline invoices", error)
		return []
	}
}

/**
 * Get count of pending offline invoices
 * @returns {Promise<number>}
 */
export const getOfflineInvoiceCount = async () => {
	try {
		return await db.invoice_queue.filter((inv) => !inv.synced).count()
	} catch (error) {
		log.error("Failed to get offline invoice count", error)
		return 0
	}
}

/**
 * Delete an offline invoice by ID
 * @param {number} id - Invoice queue ID
 * @returns {Promise<boolean>}
 */
export const deleteOfflineInvoice = async (id) => {
	try {
		await db.invoice_queue.delete(id)
		return true
	} catch (error) {
		log.error("Failed to delete offline invoice", { id, error })
		return false
	}
}

// ============================================================================
// DEDUPLICATION CHECK
// ============================================================================

/**
 * Check if an offline_id has already been synced to the server.
 * @param {string} offlineId - The offline_id to check
 * @returns {Promise<{synced: boolean, sales_invoice?: string}>}
 */
export const checkOfflineIdSynced = async (offlineId) => {
	if (!offlineId) return { synced: false }

	try {
		const response = await call(
			"pos_next.api.invoices.check_offline_invoice_synced",
			{ offline_id: offlineId },
		)
		return response || { synced: false }
	} catch (error) {
		// If check fails, assume not synced - server will still deduplicate
		log.warn("Failed to check sync status", { offline_id: offlineId, error })
		return { synced: false }
	}
}

/**
 * Check if an error message indicates a duplicate invoice
 * @param {Error|string} error - Error to check
 * @returns {{isDuplicate: boolean, invoiceName: string|null}}
 */
const checkDuplicateError = (error) => {
	const errorMessage = error?.message || error?.exc || error?.title || String(error)
	const isDuplicate = DUPLICATE_ERROR_PATTERNS.some((pattern) =>
		errorMessage.includes(pattern),
	)

	if (!isDuplicate) return { isDuplicate: false, invoiceName: null }

	const match = errorMessage.match(/Sales Invoice: (\S+)/)
	return { isDuplicate: true, invoiceName: match?.[1] || null }
}

/**
 * Check if an error indicates another request is processing the same invoice
 * @param {Error|string} error - Error to check
 * @returns {boolean}
 */
const isSyncInProgressError = (error) => {
	const errorMessage = error?.message || error?.exc || error?.title || String(error)
	return SYNC_IN_PROGRESS_PATTERNS.some((pattern) =>
		errorMessage.includes(pattern),
	)
}

/**
 * Wait for a specified duration
 * @param {number} ms - Milliseconds to wait
 * @returns {Promise<void>}
 */
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))

// ============================================================================
// SYNC OPERATIONS
// ============================================================================

/**
 * Mark an invoice as synced in the local database
 * @param {number} id - Invoice queue ID
 * @param {string} serverInvoice - Server invoice name
 */
const markInvoiceSynced = async (id, serverInvoice) => {
	await db.invoice_queue.update(id, {
		synced: true,
		server_invoice: serverInvoice,
	})
}

/**
 * Increment retry count and optionally mark as failed
 * @param {Object} invoice - Invoice record
 * @param {string} errorMessage - Error message
 */
const handleSyncFailure = async (invoice, errorMessage) => {
	const newRetryCount = (invoice.retry_count || 0) + 1
	const updates = { retry_count: newRetryCount }

	if (newRetryCount >= SYNC_CONFIG.MAX_RETRY_COUNT) {
		updates.sync_failed = true
		updates.error = errorMessage
	}

	await db.invoice_queue.update(invoice.id, updates)
}

/**
 * Convert pricing_rules to comma-separated string.
 * Returns empty string for invalid/malformed values.
 */
const stringifyPricingRules = (value) => {
	if (!value) return ''
	if (Array.isArray(value)) return value.filter(Boolean).join(',')
	if (typeof value !== 'string') return ''

	const stripped = value.trim()
	if (!stripped.startsWith('[')) return stripped

	try {
		const parsed = JSON.parse(stripped)
		if (Array.isArray(parsed)) return parsed.filter(Boolean).join(',')
	} catch (e) {
		log.warn('Invalid pricing_rules JSON, clearing value', { value: stripped.slice(0, 100) })
		return ''
	}
	return ''
}

/**
 * Normalize invoice data for server sync.
 * Items should already be formatted by formatItemsForSubmission() when saved.
 * This provides a safety net for legacy data.
 */
const normalizeInvoiceForSync = (invoiceData, offlineId) => ({
	...invoiceData,
	offline_id: offlineId || invoiceData.offline_id,
	items: invoiceData.items?.map((item) => ({
		...item,
		qty: item.qty || item.quantity || 1,
		pricing_rules: stringifyPricingRules(item.pricing_rules),
	})),
})

/**
 * Sync a single invoice to the server with retry for in-progress errors
 * @param {Object} invoice - Invoice queue record
 * @param {number} retryCount - Current retry attempt (for in-progress waits)
 * @returns {Promise<{status: 'success'|'skipped'|'failed', error?: Error}>}
 */
const syncInvoiceToServer = async (invoice, retryCount = 0) => {
	const MAX_IN_PROGRESS_RETRIES = 3
	const IN_PROGRESS_WAIT_MS = 2000  // Wait 2 seconds between retries

	const offlineId = invoice.offline_id || invoice.data?.offline_id

	// Pre-sync deduplication check
	if (offlineId) {
		const syncStatus = await checkOfflineIdSynced(offlineId)
		if (syncStatus.synced) {
			await markInvoiceSynced(invoice.id, syncStatus.sales_invoice)
			log.debug("Invoice already synced, skipping", {
				id: invoice.id,
				offline_id: offlineId,
				sales_invoice: syncStatus.sales_invoice,
			})
			return { status: "skipped" }
		}
	}

	// Prepare and submit
	const invoiceData = normalizeInvoiceForSync(invoice.data, offlineId)

	try {
		const response = await call("pos_next.api.invoices.submit_invoice", {
			data: JSON.stringify({ invoice: invoiceData, data: {} }),
		})

		if (response.message || response.name) {
			const serverName = response.name || response.message
			await markInvoiceSynced(invoice.id, serverName)
			log.success("Invoice synced", {
				id: invoice.id,
				offline_id: offlineId,
				sales_invoice: serverName,
			})
			return { status: "success" }
		}

		throw new Error("Invalid server response")
	} catch (error) {
		// Handle "sync in progress" - another request is processing this invoice
		if (isSyncInProgressError(error) && retryCount < MAX_IN_PROGRESS_RETRIES) {
			log.debug("Invoice being processed by another request, waiting...", {
				id: invoice.id,
				retry: retryCount + 1,
			})
			await sleep(IN_PROGRESS_WAIT_MS)
			return syncInvoiceToServer(invoice, retryCount + 1)
		}

		// Re-throw other errors
		throw error
	}
}

/**
 * Sync all pending offline invoices to server.
 * Uses a mutex to ensure only one sync operation runs at a time.
 * Concurrent callers will wait for the ongoing sync and receive its result.
 *
 * @returns {Promise<{success: number, failed: number, skipped: number, errors: Array}>}
 */
export const syncOfflineInvoices = async () => {
	if (isOffline()) {
		log.debug("Cannot sync while offline")
		return { success: 0, failed: 0, skipped: 0, errors: [] }
	}

	return await syncMutex.withLock(async () => {
		const pendingInvoices = await getOfflineInvoices()

		if (!pendingInvoices.length) {
			return { success: 0, failed: 0, skipped: 0, errors: [] }
		}

		log.info(`Starting sync of ${pendingInvoices.length} invoice(s)`)

		const result = { success: 0, failed: 0, skipped: 0, errors: [] }

		for (const invoice of pendingInvoices) {
			try {
				const syncResult = await syncInvoiceToServer(invoice)

				if (syncResult.status === "success") {
					result.success++
				} else if (syncResult.status === "skipped") {
					result.skipped++
				}
			} catch (error) {
				log.error("Failed to sync invoice", { id: invoice.id, error })

				// Check for duplicate error from server
				const { isDuplicate, invoiceName } = checkDuplicateError(error)
				if (isDuplicate) {
					await markInvoiceSynced(invoice.id, invoiceName)
					log.debug("Invoice is duplicate, marked as synced", { id: invoice.id })
					result.skipped++
					continue
				}

				// Handle genuine failure
				result.errors.push({
					invoiceId: invoice.id,
					offlineId: invoice.offline_id,
					customer: invoice.data?.customer || "Walk-in Customer",
					error,
				})

				await handleSyncFailure(invoice, error.message)
				result.failed++
			}
		}

		// Cleanup old synced invoices
		await cleanupSyncedInvoices()

		log.info("Sync completed", {
			success: result.success,
			skipped: result.skipped,
			failed: result.failed,
		})

		return result
	}, log.debug.bind(log))
}

/**
 * Clean up synced invoices older than configured days
 */
const cleanupSyncedInvoices = async () => {
	const cutoff = Date.now() - SYNC_CONFIG.CLEANUP_AGE_DAYS * 24 * 60 * 60 * 1000
	await db.invoice_queue
		.filter((inv) => inv.synced && inv.timestamp < cutoff)
		.delete()
}

// ============================================================================
// LOCAL STOCK OPERATIONS
// ============================================================================

/**
 * Update local stock after invoice
 * @param {Array} items - Invoice items
 */
export const updateLocalStock = async (items) => {
	if (!items?.length) return

	try {
		for (const item of items) {
			if (!item.item_code || !item.warehouse) continue

			const currentStock = await db.stock.get({
				item_code: item.item_code,
				warehouse: item.warehouse,
			})

			const qty = item.quantity || item.qty || 0
			const newQty = (currentStock?.qty || 0) - qty

			await db.stock.put({
				item_code: item.item_code,
				warehouse: item.warehouse,
				qty: newQty,
				updated_at: Date.now(),
			})
		}
	} catch (error) {
		log.error("Failed to update local stock", error)
	}
}

/**
 * Get local stock for an item
 * @param {string} itemCode - Item code
 * @param {string} warehouse - Warehouse
 * @returns {Promise<number>}
 */
export const getLocalStock = async (itemCode, warehouse) => {
	try {
		const stock = await db.stock.get({ item_code: itemCode, warehouse })
		return stock?.qty || 0
	} catch (error) {
		log.error("Failed to get local stock", { item_code: itemCode, warehouse, error })
		return 0
	}
}

// ============================================================================
// OFFLINE PAYMENT OPERATIONS
// ============================================================================

/**
 * Save payment to offline queue
 * @param {Object} paymentData - Payment data
 * @returns {Promise<boolean>}
 */
export const saveOfflinePayment = async (paymentData) => {
	const cleanData = JSON.parse(JSON.stringify(paymentData))

	await db.payment_queue.add({
		data: cleanData,
		timestamp: Date.now(),
		synced: false,
		retry_count: 0,
	})

	log.info("Payment saved to offline queue")
	return true
}

// ============================================================================
// INVOICE HISTORY CACHE OPERATIONS
// ============================================================================

/**
 * Cache invoice history for offline viewing
 * @param {Array} invoices - Array of invoice objects
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<boolean>}
 */
export const cacheInvoiceHistory = async (invoices, posProfile) => {
	if (!invoices || invoices.length === 0) return false

	try {
		// Clean data and add pos_profile for filtering
		const invoicesToCache = invoices.map((invoice) => ({
			...JSON.parse(JSON.stringify(invoice)),
			pos_profile: posProfile,
			cached_at: Date.now(),
		}))

		await db.invoice_history.bulkPut(invoicesToCache)
		log.info(`Cached ${invoices.length} invoices for offline viewing`)
		return true
	} catch (error) {
		log.error("Failed to cache invoice history", error)
		return false
	}
}

/**
 * Get cached invoice history for offline viewing
 * @param {string} posProfile - POS Profile name (optional filter)
 * @param {Object} options - Query options
 * @param {number} options.limit - Max number of invoices to return
 * @param {string} options.customer - Filter by customer name
 * @param {string} options.fromDate - Filter by posting_date >= fromDate
 * @param {string} options.toDate - Filter by posting_date <= toDate
 * @returns {Promise<Array>}
 */
export const getCachedInvoiceHistory = async (posProfile, options = {}) => {
	try {
		const { limit = 100, customer, fromDate, toDate } = options

		let query = db.invoice_history

		// Filter by POS profile if provided
		if (posProfile) {
			query = query.where("pos_profile").equals(posProfile)
		}

		let invoices = await query.toArray()

		// Apply additional filters
		if (customer) {
			invoices = invoices.filter((inv) =>
				inv.customer?.toLowerCase().includes(customer.toLowerCase()),
			)
		}

		if (fromDate) {
			invoices = invoices.filter((inv) => inv.posting_date >= fromDate)
		}

		if (toDate) {
			invoices = invoices.filter((inv) => inv.posting_date <= toDate)
		}

		// Sort by posting_date descending (newest first)
		invoices.sort((a, b) => {
			const dateA = new Date(b.posting_date + " " + (b.posting_time || "00:00:00"))
			const dateB = new Date(a.posting_date + " " + (a.posting_time || "00:00:00"))
			return dateA - dateB
		})

		return invoices.slice(0, limit)
	} catch (error) {
		log.error("Failed to get cached invoice history", error)
		return []
	}
}

/**
 * Clear cached invoice history
 * @param {string} posProfile - Optional POS Profile to clear (clears all if not provided)
 * @returns {Promise<boolean>}
 */
export const clearInvoiceHistoryCache = async (posProfile) => {
	try {
		if (posProfile) {
			await db.invoice_history.where("pos_profile").equals(posProfile).delete()
		} else {
			await db.invoice_history.clear()
		}
		log.info("Invoice history cache cleared")
		return true
	} catch (error) {
		log.error("Failed to clear invoice history cache", error)
		return false
	}
}

// ============================================================================
// UNPAID INVOICES CACHE OPERATIONS
// ============================================================================

/**
 * Cache unpaid invoices for offline viewing
 * @param {Array} invoices - Array of unpaid invoice objects
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<boolean>}
 */
export const cacheUnpaidInvoices = async (invoices, posProfile) => {
	if (!invoices || invoices.length === 0) {
		// Clear existing cache if no invoices
		try {
			await db.unpaid_invoices.where("pos_profile").equals(posProfile).delete()
		} catch (e) {
			// Ignore errors on clear
		}
		return true
	}

	try {
		// Clean data and add pos_profile for filtering
		const invoicesToCache = invoices.map((invoice) => ({
			...JSON.parse(JSON.stringify(invoice)),
			pos_profile: posProfile,
			cached_at: Date.now(),
		}))

		// Clear existing cache for this profile first
		await db.unpaid_invoices.where("pos_profile").equals(posProfile).delete()

		// Add new data
		await db.unpaid_invoices.bulkPut(invoicesToCache)
		log.info(`Cached ${invoices.length} unpaid invoices for offline viewing`)
		return true
	} catch (error) {
		log.error("Failed to cache unpaid invoices", error)
		return false
	}
}

/**
 * Get cached unpaid invoices for offline viewing
 * @param {string} posProfile - POS Profile name
 * @param {Object} options - Query options
 * @param {number} options.limit - Max number of invoices to return
 * @returns {Promise<Array>}
 */
export const getCachedUnpaidInvoices = async (posProfile, options = {}) => {
	try {
		const { limit = 100 } = options

		if (!posProfile) {
			return []
		}

		let invoices = await db.unpaid_invoices
			.where("pos_profile")
			.equals(posProfile)
			.toArray()

		// Sort by outstanding_amount descending (highest first)
		invoices.sort((a, b) => {
			const amountA = parseFloat(b.outstanding_amount || 0)
			const amountB = parseFloat(a.outstanding_amount || 0)
			return amountA - amountB
		})

		return invoices.slice(0, limit)
	} catch (error) {
		log.error("Failed to get cached unpaid invoices", error)
		return []
	}
}

/**
 * Cache unpaid invoice summary for offline viewing
 * @param {Object} summary - Summary object with count, total_outstanding, total_paid
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<boolean>}
 */
export const cacheUnpaidSummary = async (summary, posProfile) => {
	try {
		await db.settings.put({
			key: `unpaid_summary_${posProfile}`,
			value: {
				...summary,
				cached_at: Date.now(),
			},
		})
		log.debug("Cached unpaid invoice summary")
		return true
	} catch (error) {
		log.error("Failed to cache unpaid summary", error)
		return false
	}
}

/**
 * Get cached unpaid invoice summary
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<Object>}
 */
export const getCachedUnpaidSummary = async (posProfile) => {
	try {
		const result = await db.settings.get(`unpaid_summary_${posProfile}`)
		return result?.value || { count: 0, total_outstanding: 0, total_paid: 0 }
	} catch (error) {
		log.error("Failed to get cached unpaid summary", error)
		return { count: 0, total_outstanding: 0, total_paid: 0 }
	}
}
