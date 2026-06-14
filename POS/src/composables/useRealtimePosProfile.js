/**
 * @fileoverview Real-time POS Profile Updates Composable
 *
 * Manages real-time synchronization of POS Profile configuration changes across
 * connected clients via Socket.IO. Implements singleton pattern for efficient
 * event handling and provides automatic lifecycle management.
 *
 * Key Features:
 * - Singleton event listener (shared across all component instances)
 * - Automatic connection/disconnection based on handler count
 * - Memory leak prevention with proper cleanup
 * - Defensive error handling with handler isolation
 * - Type-safe event payload validation
 * - Debounced event processing for high-frequency updates
 * - Graceful degradation when Socket.IO unavailable
 *
 * @module composables/useRealtimePosProfile
 */

import { logger } from "@/utils/logger"
import { readonly, ref } from "vue"

const log = logger.create('RealtimePosProfile')

// ============================================================================
// CONSTANTS
// ============================================================================

const EVENT_NAME = "pos_profile_updated"
const DEBOUNCE_DELAY_MS = 300 // Prevent rapid-fire updates
const MAX_RETRY_ATTEMPTS = 3
const RETRY_DELAY_MS = 1000

// ============================================================================
// SINGLETON STATE (shared across all component instances)
// ============================================================================

/** @type {import('vue').Ref<boolean>} */
const isListening = ref(false)

/** @type {import('vue').Ref<boolean>} */
const isConnecting = ref(false)

/** @type {Set<Function>} Registered event handlers */
const eventHandlers = new Set()

/** @type {Map<string, NodeJS.Timeout>} Debounce timers per profile */
const debounceTimers = new Map()

/** @type {number} Connection retry attempts */
let retryAttempts = 0

/** @type {NodeJS.Timeout|null} Retry timer */
let retryTimer = null

// ============================================================================
// INTERNAL HELPERS
// ============================================================================

/**
 * Validates event payload structure
 * @param {any} data - Event payload to validate
 * @returns {boolean} True if valid
 */
function isValidEventPayload(data) {
	if (!data || typeof data !== "object") {
		log.warn("Invalid event payload: not an object", { data })
		return false
	}

	if (!data.pos_profile || typeof data.pos_profile !== "string") {
		log.warn("Invalid event payload: missing or invalid pos_profile", { data })
		return false
	}

	return true
}

/**
 * Executes handler with error isolation
 * Ensures one failing handler doesn't break others
 * @param {Function} handler - Handler to execute
 * @param {Object} data - Event data
 */
async function executeHandlerSafely(handler, data) {
	try {
		await Promise.resolve(handler(data))
	} catch (error) {
		log.error("Handler execution failed", {
			error: error.message,
			stack: error.stack,
			profile: data.pos_profile
		})
		// Don't rethrow - isolate handler errors
	}
}

/**
 * Core event handler with debouncing and validation
 * @param {Object} data - Event payload from Socket.IO
 */
function handlePosProfileUpdate(data) {
	// Validate payload
	if (!isValidEventPayload(data)) {
		return
	}

	const { pos_profile, change_type, item_groups, timestamp } = data

	log.info("POS Profile update received", {
		profile: pos_profile,
		changeType: change_type,
		itemGroupCount: item_groups?.length ?? 0,
		timestamp,
		handlerCount: eventHandlers.size
	})

	// Debounce updates per profile (prevent rapid-fire changes)
	const existingTimer = debounceTimers.get(pos_profile)
	if (existingTimer) {
		clearTimeout(existingTimer)
	}

	const timer = setTimeout(() => {
		debounceTimers.delete(pos_profile)

		// Execute all registered handlers in parallel with error isolation
		const handlerPromises = Array.from(eventHandlers).map(handler =>
			executeHandlerSafely(handler, data)
		)

		Promise.all(handlerPromises).then(() => {
			log.debug("All handlers executed", {
				profile: pos_profile,
				handlerCount: eventHandlers.size
			})
		})
	}, DEBOUNCE_DELAY_MS)

	debounceTimers.set(pos_profile, timer)
}

/**
 * Checks if Socket.IO is available and connected
 * @returns {boolean}
 */
function isSocketAvailable() {
	if (typeof window === "undefined") {
		log.warn("Window object not available (SSR context)")
		return false
	}

	if (!window.frappe?.realtime) {
		log.warn("Socket.IO client not initialized (window.frappe.realtime)")
		return false
	}

	return true
}

/**
 * Starts listening to real-time events
 * Implements retry logic for connection failures
 */
function startListening() {
	// Prevent concurrent connection attempts
	if (isListening.value || isConnecting.value) {
		log.debug("Already listening or connecting")
		return
	}

	if (!isSocketAvailable()) {
		// Schedule retry if we haven't exceeded max attempts
		if (retryAttempts < MAX_RETRY_ATTEMPTS) {
			retryAttempts++
			const delay = RETRY_DELAY_MS * retryAttempts

			log.info(`Socket unavailable, retrying in ${delay}ms (attempt ${retryAttempts}/${MAX_RETRY_ATTEMPTS})`)

			retryTimer = setTimeout(() => {
				startListening()
			}, delay)
		} else {
			log.error(`Failed to connect after ${MAX_RETRY_ATTEMPTS} attempts`)
		}
		return
	}

	try {
		isConnecting.value = true

		// Subscribe to POS Profile update events
		window.frappe.realtime.on(EVENT_NAME, handlePosProfileUpdate)

		isListening.value = true
		isConnecting.value = false
		retryAttempts = 0 // Reset on success

		log.success("Started listening to POS Profile updates", {
			event: EVENT_NAME,
			handlerCount: eventHandlers.size
		})
	} catch (error) {
		isConnecting.value = false
		log.error("Failed to start listening", error)

		// Retry on error
		if (retryAttempts < MAX_RETRY_ATTEMPTS) {
			retryAttempts++
			retryTimer = setTimeout(() => startListening(), RETRY_DELAY_MS)
		}
	}
}

/**
 * Stops listening to real-time events and cleans up resources
 */
function stopListening() {
	// Clear retry timer if pending
	if (retryTimer) {
		clearTimeout(retryTimer)
		retryTimer = null
	}

	// Clear debounce timers
	debounceTimers.forEach(timer => clearTimeout(timer))
	debounceTimers.clear()

	if (!isListening.value) {
		log.debug("Not currently listening")
		return
	}

	try {
		if (isSocketAvailable()) {
			window.frappe.realtime.off(EVENT_NAME, handlePosProfileUpdate)
		}

		isListening.value = false
		retryAttempts = 0

		log.info("Stopped listening to POS Profile updates")
	} catch (error) {
		// Ensure state is cleaned up even if unsubscribe fails
		isListening.value = false
		log.error("Error while stopping listener", error)
	}
}

/**
 * Force immediate reconnection (useful after network recovery)
 */
function reconnect() {
	log.info("Forcing reconnection")
	stopListening()
	retryAttempts = 0
	startListening()
}

// ============================================================================
// PUBLIC API
// ============================================================================

/**
 * Composable for real-time POS Profile updates
 * @returns {Object} Composable API
 */
export function useRealtimePosProfile() {
	/**
	 * Registers a callback to be notified of POS Profile updates
	 * Automatically starts listening when first handler is registered
	 *
	 * @param {Function} handler - Async handler function: (data) => Promise<void>
	 * @returns {Function} Cleanup function to unregister handler
	 * @throws {TypeError} If handler is not a function
	 *
	 * @example
	 * const cleanup = onPosProfileUpdate(async (data) => {
	 *   if (data.pos_profile === currentProfile.value) {
	 *     await updateCache(data.item_groups)
	 *   }
	 * })
	 *
	 * // Later: cleanup()
	 */
	function onPosProfileUpdate(handler) {
		// Type validation
		if (typeof handler !== "function") {
			throw new TypeError(`Handler must be a function, received: ${typeof handler}`)
		}

		// Prevent duplicate registration
		if (eventHandlers.has(handler)) {
			log.warn("Handler already registered (duplicate)")
			return () => {} // Return no-op cleanup
		}

		eventHandlers.add(handler)

		log.debug("Handler registered", {
			handlerCount: eventHandlers.size
		})

		// Auto-start listening when first handler is registered
		if (eventHandlers.size === 1) {
			startListening()
		}

		// Return cleanup function
		return () => {
			eventHandlers.delete(handler)

			log.debug("Handler unregistered", {
				handlerCount: eventHandlers.size
			})

			// Auto-stop listening when last handler is removed
			if (eventHandlers.size === 0) {
				stopListening()
			}
		}
	}

	/**
	 * Gets current handler count (useful for debugging)
	 * @returns {number}
	 */
	function getHandlerCount() {
		return eventHandlers.size
	}

	/**
	 * Clears all handlers (useful for testing)
	 */
	function clearAllHandlers() {
		log.warn("Clearing all handlers", {
			count: eventHandlers.size
		})
		eventHandlers.clear()
		stopListening()
	}

	// Return public API with readonly refs to prevent external mutation
	return {
		// State (readonly to prevent external mutation)
		isListening: readonly(isListening),
		isConnecting: readonly(isConnecting),

		// Primary API
		onPosProfileUpdate,

		// Control methods (typically not needed - auto-managed)
		startListening,
		stopListening,
		reconnect,

		// Utility methods (primarily for debugging/testing)
		getHandlerCount,
		clearAllHandlers,
	}
}
