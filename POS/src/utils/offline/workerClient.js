/**
 * Worker Client - Main thread interface to offline worker
 * Provides promise-based API to communicate with offline worker
 * Enhanced with retry logic, graceful degradation, and error recovery
 */

import { logger } from '../logger'
const log = logger.create('OfflineWorker')

class OfflineWorkerClient {
	constructor() {
		this.worker = null
		this.messageId = 0
		this.pendingMessages = new Map()
		this.ready = false
		this.serverOnline = true
		this.retryAttempts = new Map() // Track retry attempts per message type
		this.workerCrashed = false
		this.initAttempts = 0
		this.maxInitAttempts = 3
		this.healthCheckInterval = null
		this.healthCheckActive = false // Prevent double-initialization
		this.lastHealthCheck = Date.now()

		// Retry configuration
		this.maxRetries = 3
		this.retryDelay = 1000 // Base delay in ms
		this.retryMultiplier = 2 // Exponential backoff multiplier
	}

	init() {
		if (this.worker && !this.workerCrashed) return

		// Check if we've exceeded max init attempts
		if (this.initAttempts >= this.maxInitAttempts) {
			log.error("Max initialization attempts reached, using graceful degradation")
			this.workerCrashed = true
			this.rejectAllPending("Worker failed to initialize after multiple attempts")
			return
		}

		try {
			this.initAttempts++
			this.workerCrashed = false

			// Create worker using Vite's worker import syntax
			this.worker = new Worker(
				new URL("../../workers/offline.worker.js?worker", import.meta.url),
				{ type: "module" },
			)

			// Handle messages from worker
			this.worker.onmessage = (event) => {
				this.lastHealthCheck = Date.now()
				const { type, id, payload } = event.data

				if (type === "WORKER_READY") {
					this.ready = true
					this.serverOnline = payload.serverOnline
					this.initAttempts = 0 // Reset on successful init
					this.startHealthCheck()
					log.success("Offline worker ready", { serverOnline: payload.serverOnline })
					return
				}

				if (type === "SERVER_STATUS_CHANGE") {
					this.serverOnline = payload.serverOnline
					// Emit custom event for status changes
					window.dispatchEvent(
						new CustomEvent("offlineStatusChange", {
							detail: { serverOnline: payload.serverOnline },
						}),
					)
					return
				}

				if (type === "STOCK_SYNC_COMPLETE") {
					// Emit custom event for stock sync completion
					window.dispatchEvent(
						new CustomEvent("stockSyncComplete", {
							detail: payload,
						}),
					)
					return
				}

				if (type === "STOCK_SYNC_ERROR") {
					// Emit custom event for stock sync errors
					window.dispatchEvent(
						new CustomEvent("stockSyncError", {
							detail: payload,
						}),
					)
					return
				}

				if (id !== undefined && this.pendingMessages.has(id)) {
					const { resolve, reject, messageType, payload: originalPayload } = this.pendingMessages.get(id)
					this.pendingMessages.delete(id)

					if (type === "SUCCESS") {
						// Clear retry count on success
						this.retryAttempts.delete(messageType)
						resolve(payload)
					} else if (type === "ERROR") {
						// Check if we should retry
						const shouldRetry = this.shouldRetryMessage(messageType, payload)
						if (shouldRetry) {
							// CRITICAL FIX: Use original payload, not error payload
							this.retryMessage(id, messageType, originalPayload, resolve, reject)
						} else {
							this.retryAttempts.delete(messageType)
							reject(new Error(payload.message))
						}
					}
				}
			}

			// Handle worker errors - crash recovery
			this.worker.onerror = (error) => {
				log.error("Worker error", {
					message: error.message,
					filename: error.filename,
					lineno: error.lineno,
					colno: error.colno,
				})

				this.handleWorkerCrash("Worker error", error.message)
			}

			// Handle worker termination
			this.worker.onmessageerror = (error) => {
				log.error("Worker message error", error)
				this.handleWorkerCrash("Worker message error", error.message)
			}
		} catch (error) {
			log.error("Failed to create worker", error)
			this.handleWorkerCrash("Worker creation failed", error.message)
		}
	}

	/**
	 * Start health check interval to detect unresponsive worker
	 */
	startHealthCheck() {
		// Prevent double-initialization (memory leak fix)
		if (this.healthCheckActive) {
			return
		}

		// Clear any existing interval
		if (this.healthCheckInterval) {
			clearInterval(this.healthCheckInterval)
			this.healthCheckInterval = null
		}

		// Mark as active
		this.healthCheckActive = true

		// Check worker health every 60 seconds
		this.healthCheckInterval = setInterval(() => {
			const timeSinceLastMessage = Date.now() - this.lastHealthCheck

			// If no message received in 2 minutes and we have pending messages, worker might be hung
			if (timeSinceLastMessage > 120000 && this.pendingMessages.size > 0) {
				log.warn("Worker appears unresponsive, attempting recovery")
				this.handleWorkerCrash("Worker unresponsive", "No messages received for 2 minutes")
			}
		}, 60000)
	}

	/**
	 * Determine if a message should be retried
	 */
	shouldRetryMessage(messageType, errorPayload) {
		// Don't retry certain error types
		const nonRetryableErrors = [
			"QuotaExceededError",
			"Invalid invoice",
			"Cannot save empty invoice",
		]

		if (nonRetryableErrors.some(err => errorPayload.message?.includes(err))) {
			return false
		}

		const currentRetries = this.retryAttempts.get(messageType) || 0
		return currentRetries < this.maxRetries
	}

	/**
	 * Retry a failed message with exponential backoff
	 */
	async retryMessage(originalId, messageType, originalPayload, resolve, reject) {
		const currentRetries = this.retryAttempts.get(messageType) || 0
		this.retryAttempts.set(messageType, currentRetries + 1)

		const delay = this.retryDelay * Math.pow(this.retryMultiplier, currentRetries)
		log.info(`Retrying ${messageType} in ${delay}ms`, { attempt: currentRetries + 1, maxRetries: this.maxRetries })

		setTimeout(async () => {
			try {
				const result = await this.sendMessage(messageType, originalPayload, true)
				this.retryAttempts.delete(messageType)
				resolve(result)
			} catch (error) {
				reject(error)
			}
		}, delay)
	}

	/**
	 * Handle worker crash and attempt recovery
	 */
	handleWorkerCrash(reason, details) {
		log.error(`Worker crashed: ${reason}`, details)
		this.workerCrashed = true
		this.ready = false

		// Stop health check
		if (this.healthCheckInterval) {
			clearInterval(this.healthCheckInterval)
			this.healthCheckInterval = null
		}
		this.healthCheckActive = false

		// Reject all pending messages
		this.rejectAllPending(`Worker crashed: ${reason}`)

		// Terminate crashed worker
		if (this.worker) {
			try {
				this.worker.terminate()
			} catch (e) {
				log.error("Error terminating crashed worker", e)
			}
			this.worker = null
		}

		// Attempt to restart worker after a delay
		if (this.initAttempts < this.maxInitAttempts) {
			const restartDelay = 2000 * Math.pow(2, this.initAttempts)
			log.info(`Attempting worker restart in ${restartDelay}ms`)

			setTimeout(() => {
				this.init()
			}, restartDelay)
		}
	}

	/**
	 * Reject all pending messages with error
	 */
	rejectAllPending(reason) {
		const error = new Error(reason)
		for (const [id, { reject }] of this.pendingMessages) {
			reject(error)
		}
		this.pendingMessages.clear()
	}

	async sendMessage(type, payload = {}, isRetry = false) {
		// If worker has permanently failed, return graceful degradation
		if (this.workerCrashed && this.initAttempts >= this.maxInitAttempts) {
			log.warn(`Worker unavailable, gracefully degrading for: ${type}`)
			return this.gracefulFallback(type, payload)
		}

		// If worker needs initialization, wait for it properly
		if (!this.worker || this.workerCrashed) {
			this.init()
			// Wait for worker to be ready or fail (with timeout)
			const maxWaitTime = 5000 // 5 seconds max wait
			const startTime = Date.now()

			while (!this.ready && !this.workerCrashed && (Date.now() - startTime) < maxWaitTime) {
				await new Promise(resolve => setTimeout(resolve, 50))
			}

			// If still not ready after timeout, use fallback
			if (!this.ready || !this.worker) {
				log.warn(`Worker not ready after ${maxWaitTime}ms, using fallback for: ${type}`)
				return this.gracefulFallback(type, payload)
			}
		}

		return new Promise((resolve, reject) => {
			const id = this.messageId++
			this.pendingMessages.set(id, {
				resolve,
				reject,
				messageType: type,
				payload,
				timestamp: Date.now(),
				retryCount: isRetry ? ((this.retryAttempts.get(type) || 0)) : 0
			})

			try {
				this.worker.postMessage({ type, payload, id })
			} catch (error) {
				this.pendingMessages.delete(id)
				reject(new Error(`Failed to post message: ${error.message}`))
				return
			}

			// Timeout after 30 seconds
			setTimeout(() => {
				if (this.pendingMessages.has(id)) {
					const messageInfo = this.pendingMessages.get(id)
					this.pendingMessages.delete(id)

					// IMPORTANT: Prevent infinite retries by checking retry flag AND count
					// Only retry if: not already a retry AND haven't exceeded max retries
					const currentRetries = messageInfo.retryCount || 0
					if (!isRetry && currentRetries < this.maxRetries && this.shouldRetryMessage(type, { message: "timeout" })) {
						this.retryMessage(id, type, payload, resolve, reject)
					} else {
						reject(new Error(`Worker message timeout: ${type} (retries: ${currentRetries})`))
					}
				}
			}, 30000)
		})
	}

	/**
	 * Graceful fallback when worker is unavailable
	 * Returns empty/default values instead of throwing errors
	 */
	gracefulFallback(type, payload) {
		log.warn(`Graceful fallback for ${type}`)

		switch (type) {
			case "GET_INVOICE_COUNT":
				return 0
			case "GET_INVOICES":
			case "SEARCH_ITEMS":
			case "SEARCH_CUSTOMERS":
			case "GET_PAYMENT_METHODS":
				return []
			case "IS_CACHE_READY":
				return false
			case "GET_CACHE_STATS":
				return {
					items: 0,
					customers: 0,
					queuedInvoices: 0,
					cacheReady: false,
					lastSync: null
				}
			case "PING_SERVER":
			case "CHECK_OFFLINE":
				return true // Assume offline when worker unavailable
			case "SAVE_INVOICE":
			case "DELETE_INVOICE":
			case "CACHE_ITEMS":
			case "CACHE_CUSTOMERS":
			case "CACHE_PAYMENT_METHODS":
			case "UPDATE_STOCK_QUANTITIES":
			case "CLEAR_ITEMS_CACHE":
			case "CLEAR_CUSTOMERS_CACHE":
			case "REMOVE_ITEMS_BY_GROUPS":
				// For write operations, throw error so caller knows to handle differently
				throw new Error(`Worker unavailable: Cannot perform ${type}`)
			default:
				throw new Error(`Worker unavailable: Unknown operation ${type}`)
		}
	}

	// API Methods
	async pingServer() {
		return this.sendMessage("PING_SERVER")
	}

	async checkOffline(browserOnline) {
		return this.sendMessage("CHECK_OFFLINE", { browserOnline })
	}

	async getOfflineInvoiceCount() {
		return this.sendMessage("GET_INVOICE_COUNT")
	}

	async getOfflineInvoices() {
		return this.sendMessage("GET_INVOICES")
	}

	async saveOfflineInvoice(invoiceData) {
		return this.sendMessage("SAVE_INVOICE", { invoiceData })
	}

	async searchCachedItems(searchTerm = "", limit = 50) {
		return this.sendMessage("SEARCH_ITEMS", { searchTerm, limit })
	}

	async searchCachedCustomers(searchTerm = "", limit = 20) {
		return this.sendMessage("SEARCH_CUSTOMERS", { searchTerm, limit })
	}

	async cacheItems(items) {
		return this.sendMessage("CACHE_ITEMS", { items })
	}

	async cacheCustomers(customers) {
		return this.sendMessage("CACHE_CUSTOMERS", { customers })
	}

	async cachePaymentMethods(paymentMethods) {
		return this.sendMessage("CACHE_PAYMENT_METHODS", { paymentMethods })
	}

	async getCachedPaymentMethods(posProfile) {
		return this.sendMessage("GET_PAYMENT_METHODS", { posProfile })
	}

	async isCacheReady() {
		return this.sendMessage("IS_CACHE_READY")
	}

	async getCacheStats() {
		return this.sendMessage("GET_CACHE_STATS")
	}

	async deleteOfflineInvoice(id) {
		return this.sendMessage("DELETE_INVOICE", { id })
	}

	async setManualOffline(value) {
		return this.sendMessage("SET_MANUAL_OFFLINE", { value })
	}

	async setCSRFToken(token) {
		return this.sendMessage("SET_CSRF_TOKEN", { token })
	}

	async updateStockQuantities(stockUpdates) {
		return this.sendMessage("UPDATE_STOCK_QUANTITIES", { stockUpdates })
	}

	async clearItemsCache() {
		return this.sendMessage("CLEAR_ITEMS_CACHE")
	}

	async clearCustomersCache() {
		return this.sendMessage("CLEAR_CUSTOMERS_CACHE")
	}

	async removeItemsByGroups(itemGroups) {
		return this.sendMessage("REMOVE_ITEMS_BY_GROUPS", { itemGroups })
	}

	// ========================================================================
	// PERIODIC STOCK SYNC API
	// ========================================================================

	/**
	 * Start periodic stock sync in background worker
	 * @returns {Promise<{success: boolean, status: Object}>}
	 */
	async startStockSync() {
		return this.sendMessage("START_STOCK_SYNC")
	}

	/**
	 * Stop periodic stock sync
	 * @returns {Promise<{success: boolean, status: Object}>}
	 */
	async stopStockSync() {
		return this.sendMessage("STOP_STOCK_SYNC")
	}

	/**
	 * Configure periodic stock sync
	 * @param {Object} config - Configuration object
	 * @param {string} config.warehouse - Warehouse to track
	 * @param {Array<string>} config.itemCodes - Item codes to sync
	 * @param {number} config.intervalMs - Sync interval in milliseconds (min 10000)
	 * @returns {Promise<Object>} Current configuration
	 */
	async configureStockSync({ warehouse, itemCodes, intervalMs }) {
		return this.sendMessage("CONFIGURE_STOCK_SYNC", { warehouse, itemCodes, intervalMs })
	}

	/**
	 * Get current stock sync status
	 * @returns {Promise<Object>} Status object
	 */
	async getStockSyncStatus() {
		return this.sendMessage("GET_STOCK_SYNC_STATUS")
	}

	/**
	 * Manually trigger a stock sync cycle (one-time)
	 * @returns {Promise<{success: boolean, status: Object}>}
	 */
	async triggerStockSync() {
		return this.sendMessage("TRIGGER_STOCK_SYNC")
	}

	terminate() {
		// Stop health check
		if (this.healthCheckInterval) {
			clearInterval(this.healthCheckInterval)
			this.healthCheckInterval = null
		}
		this.healthCheckActive = false

		// Reject pending messages
		this.rejectAllPending("Worker terminated")

		// Terminate worker
		if (this.worker) {
			this.worker.terminate()
			this.worker = null
			this.ready = false
		}

		// Reset state
		this.workerCrashed = false
		this.initAttempts = 0
		this.retryAttempts.clear()
	}
}

// Create singleton instance
export const offlineWorker = new OfflineWorkerClient()

// Initialize worker on import
if (typeof window !== "undefined") {
	offlineWorker.init()
}
