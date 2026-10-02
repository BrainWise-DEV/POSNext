/**
 * @fileoverview Real-time Customer Updates Composable
 *
 * Manages real-time synchronization of Customer changes across
 * connected clients via Socket.IO. Implements singleton pattern for efficient
 * event handling and provides automatic lifecycle management.
 *
 * @module composables/useRealtimeCustomers
 */

import { logger } from "@/utils/logger"
import { readonly, ref } from "vue"

const log = logger.create('RealtimeCustomers')

// ============================================================================
// CONSTANTS
// ============================================================================

const EVENT_NAME = "pos_customer_changed"
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

/** @type {Map<string, NodeJS.Timeout>} Debounce timers per customer */
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

    if (!data.name || typeof data.name !== "string") {
        log.warn("Invalid event payload: missing or invalid customer ID (name)", { data })
        return false
    }

    return true
}

/**
 * Executes handler with error isolation
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
            customer: data.name
        })
    }
}

/**
 * Core event handler with debouncing and validation
 * @param {Object} data - Event payload from Socket.IO
 */
function handleCustomerUpdate(data) {
    if (!isValidEventPayload(data)) {
        console.log("Invalid event payload", data)
        return
    }

    const { name, action, timestamp } = data

    log.info("Customer update received", {
        customer: name,
        action,
        timestamp,
        handlerCount: eventHandlers.size
    })

    // Debounce updates per customer
    const existingTimer = debounceTimers.get(name)
    if (existingTimer) {
        clearTimeout(existingTimer)
    }

    const timer = setTimeout(() => {
        debounceTimers.delete(name)

        // Execute all registered handlers in parallel with error isolation
        const handlerPromises = Array.from(eventHandlers).map(handler =>
            executeHandlerSafely(handler, data)
        )

        Promise.all(handlerPromises).then(() => {
            log.debug("All handlers executed", {
                customer: name,
                handlerCount: eventHandlers.size
            })
        })
    }, DEBOUNCE_DELAY_MS)

    debounceTimers.set(name, timer)
}

/**
 * Checks if Socket.IO is available
 * @returns {boolean}
 */
function isSocketAvailable() {
    return !!(typeof window !== "undefined" && window.frappe?.realtime)
}

/**
 * Starts listening to real-time events
 */
function startListening() {
    if (isListening.value || isConnecting.value) return

    if (!isSocketAvailable()) {
        if (retryAttempts < MAX_RETRY_ATTEMPTS) {
            retryAttempts++
            retryTimer = setTimeout(() => startListening(), RETRY_DELAY_MS * retryAttempts)
        }
        return
    }

    try {
        isConnecting.value = true
        window.frappe.realtime.on(EVENT_NAME, handleCustomerUpdate)
        isListening.value = true
        isConnecting.value = false
        retryAttempts = 0
        log.success("Started listening to Customer updates", { event: EVENT_NAME })
    } catch (error) {
        isConnecting.value = false
        log.error("Failed to start listening", error)
        if (retryAttempts < MAX_RETRY_ATTEMPTS) {
            retryAttempts++
            retryTimer = setTimeout(() => startListening(), RETRY_DELAY_MS)
        }
    }
}

/**
 * Stops listening to real-time events
 */
function stopListening() {
    if (retryTimer) {
        clearTimeout(retryTimer)
        retryTimer = null
    }
    debounceTimers.forEach(timer => clearTimeout(timer))
    debounceTimers.clear()

    if (!isListening.value) return

    try {
        if (isSocketAvailable()) {
            window.frappe.realtime.off(EVENT_NAME, handleCustomerUpdate)
        }
        isListening.value = false
        retryAttempts = 0
        log.info("Stopped listening to Customer updates")
    } catch (error) {
        isListening.value = false
        log.error("Error while stopping listener", error)
    }
}

// ============================================================================
// PUBLIC API
// ============================================================================

/**
 * Composable for real-time Customer updates
 * @returns {Object} Composable API
 */
export function useRealtimeCustomers() {
    /**
     * Registers a callback to be notified of Customer changes
     * @param {Function} handler - Async handler function: (data) => Promise<void>
     * @returns {Function} Cleanup function
     */
    function onCustomerUpdate(handler) {
        if (typeof handler !== "function") {
            throw new TypeError(`Handler must be a function`)
        }

        if (eventHandlers.has(handler)) return () => { }

        eventHandlers.add(handler)

        if (eventHandlers.size === 1) {
            startListening()
        }

        return () => {
            eventHandlers.delete(handler)
            if (eventHandlers.size === 0) {
                stopListening()
            }
        }
    }

    return {
        isListening: readonly(isListening),
        isConnecting: readonly(isConnecting),
        onCustomerUpdate,
    }
}
