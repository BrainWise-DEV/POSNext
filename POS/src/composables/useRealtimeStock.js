/**
 * Real-time Stock Updates Composable
 *
 * Listens to Socket.IO events for stock changes and notifies registered handlers.
 * Provides intelligent event management with deduplication and batching.
 * Each handler is responsible for filtering by warehouse and updating its cache.
 *
 * Performance optimization: Batch delay and size are dynamically adjusted
 * based on device CPU cores and performance tier.
 */

import { performanceConfig } from "@/utils/performanceConfig"
import { logger } from "@/utils/logger"
import { ref } from "vue"

const log = logger.create('RealtimeStock')

// Shared state across all instances
const isListening = ref(false)
const eventHandlers = new Set()
const pendingUpdates = new Map()
let batchTimeout = null

/**
 * Batch update configuration - dynamically adjusted based on device performance
 * Low-end devices (800ms, 50 items): More batching to reduce CPU load
 * Medium devices (500ms, 100 items): Balanced performance
 * High-end devices (300ms, 200 items): Faster updates with larger batches
 */
const BATCH_DELAY_MS = performanceConfig.get("stockBatchDelay")
const MAX_BATCH_SIZE = performanceConfig.get("stockMaxBatchSize")

/**
 * Process pending stock updates in batch
 */
async function processBatchedUpdates() {
	if (pendingUpdates.size === 0) {
		return
	}

	const updates = Array.from(pendingUpdates.values())
	pendingUpdates.clear()

	try {
		// Notify all registered handlers
		// Each handler can filter by warehouse before applying updates
		eventHandlers.forEach((handler) => {
			try {
				handler(updates)
			} catch (error) {
				log.error("Handler error", error)
			}
		})
	} catch (error) {
		log.error("Failed to process batch updates", error)
	}
}

/**
 * Schedule batch processing
 */
function scheduleBatchUpdate() {
	if (batchTimeout) {
		clearTimeout(batchTimeout)
	}

	// Force update if batch is getting too large
	if (pendingUpdates.size >= MAX_BATCH_SIZE) {
		processBatchedUpdates()
		return
	}

	batchTimeout = setTimeout(() => {
		processBatchedUpdates()
		batchTimeout = null
	}, BATCH_DELAY_MS)
}

/**
 * Handle incoming stock update event
 */
function handleStockUpdate(data) {
	if (!data || !data.stock_updates) {
		return
	}

	// Add updates to pending batch (deduplicate by item_code + warehouse)
	data.stock_updates.forEach((update) => {
		const key = `${update.item_code}|${update.warehouse}`
		pendingUpdates.set(key, update)
	})

	scheduleBatchUpdate()
}

/**
 * Handle invoice created event (optional, for future use)
 */
function handleInvoiceCreated(data) {
	// Can be used to update sales dashboards, notifications, etc.
}

/**
 * Start listening to real-time events
 */
function startListening() {
	if (isListening.value) {
		return
	}

	if (!window.frappe?.realtime) {
		log.warn("Socket.IO not available")
		return
	}

	// Subscribe to stock update events
	window.frappe.realtime.on("pos_stock_update", handleStockUpdate)
	window.frappe.realtime.on("pos_invoice_created", handleInvoiceCreated)

	isListening.value = true
}

/**
 * Stop listening to real-time events
 */
function stopListening() {
	if (!isListening.value) {
		return
	}

	if (window.frappe?.realtime) {
		window.frappe.realtime.off("pos_stock_update", handleStockUpdate)
		window.frappe.realtime.off("pos_invoice_created", handleInvoiceCreated)
	}

	// Clear pending updates
	if (batchTimeout) {
		clearTimeout(batchTimeout)
		batchTimeout = null
	}
	pendingUpdates.clear()

	isListening.value = false
}

/**
 * Flush pending updates immediately
 */
async function flushUpdates() {
	if (batchTimeout) {
		clearTimeout(batchTimeout)
		batchTimeout = null
	}
	await processBatchedUpdates()
}

/**
 * Main composable
 */
export function useRealtimeStock() {
	/**
	 * Register a callback to be notified of stock updates
	 * @param {Function} handler - Called with array of stock updates
	 * @returns {Function} Cleanup function to unregister handler
	 */
	function onStockUpdate(handler) {
		if (typeof handler !== "function") {
			throw new Error("Handler must be a function")
		}

		eventHandlers.add(handler)

		// Start listening when first handler is registered
		if (eventHandlers.size === 1) {
			startListening()
		}

		// Return cleanup function
		return () => {
			eventHandlers.delete(handler)

			// Stop listening when last handler is removed
			if (eventHandlers.size === 0) {
				stopListening()
			}
		}
	}

	// Note: Each handler is responsible for its own cleanup via the returned cleanup function.
	// The singleton listener remains active as long as there are registered handlers.

	return {
		isListening,
		onStockUpdate,
		flushUpdates,
		startListening,
		stopListening,
	}
}
