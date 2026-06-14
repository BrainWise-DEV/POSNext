/**
 * POS Events Store - Centralized Event Management
 *
 * This store provides a reactive event bus for handling settings changes
 * and other system-wide events without requiring page reloads.
 *
 * Event Types:
 * - settings:changed - When any POS setting is updated
 * - settings:warehouse-changed - When warehouse is changed
 * - settings:stock-policy-changed - When stock validation policy changes
 * - settings:pricing-changed - When pricing/discount settings change
 * - settings:sync-configured - When background sync settings change
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { logger } from '@/utils/logger'

const log = logger.create('POSEvents')
const byteToHex = Array.from({ length: 256 }, (_, i) => i.toString(16).padStart(2, '0'))

/**
 * Generate a UUID with fallback for environments that don't support crypto.randomUUID
 * @returns {string} - A unique identifier
 */
function generateUUID() {
	const cryptoSource = typeof globalThis !== 'undefined' && globalThis.crypto
		? globalThis.crypto
		: (typeof window !== 'undefined' ? window.crypto : undefined)

	if (cryptoSource?.randomUUID) {
		try {
			return cryptoSource.randomUUID()
		} catch (error) {
			log.warn('crypto.randomUUID failed, falling back to manual generation', error)
		}
	}

	const getRandomValues = cryptoSource?.getRandomValues?.bind(cryptoSource)
	if (getRandomValues && typeof Uint8Array !== 'undefined') {
		const bytes = getRandomValues(new Uint8Array(16))
		bytes[6] = bytes[6] & 0x0f | 0x40
		bytes[8] = bytes[8] & 0x3f | 0x80

		const hex = Array.from(bytes, byte => byteToHex[byte]).join('')
		return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
	}

	return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
		const r = Math.random() * 16 | 0
		const v = c === 'x' ? r : (r & 0x3 | 0x8)
		return v.toString(16)
	})
}

export const usePOSEventsStore = defineStore('posEvents', () => {
	// ========================================================================
	// STATE - Event Tracking
	// ========================================================================
	const eventHistory = ref([])
	const listeners = ref(new Map()) // eventType -> Set<callback>
	const maxHistorySize = ref(100)

	// Settings-specific state for tracking changes
	const lastSettingsSnapshot = ref(null)
	const pendingReloads = ref(new Set())

	// ========================================================================
	// COMPUTED
	// ========================================================================
	const recentEvents = computed(() => eventHistory.value.slice(0, 20))

	const hasPendingReloads = computed(() => pendingReloads.value.size > 0)

	// ========================================================================
	// CORE EVENT SYSTEM
	// ========================================================================

	/**
	 * Register an event listener
	 * @param {string} eventType - The event type to listen for
	 * @param {Function} callback - The callback function
	 * @returns {Function} - Unsubscribe function
	 */
	function on(eventType, callback) {
		if (!listeners.value.has(eventType)) {
			listeners.value.set(eventType, new Set())
		}

		listeners.value.get(eventType).add(callback)

		log.debug(`Listener registered for: ${eventType}`)

		// Return unsubscribe function
		return () => off(eventType, callback)
	}

	/**
	 * Remove an event listener
	 * @param {string} eventType - The event type
	 * @param {Function} callback - The callback function to remove
	 */
	function off(eventType, callback) {
		if (listeners.value.has(eventType)) {
			listeners.value.get(eventType).delete(callback)
			log.debug(`Listener removed for: ${eventType}`)
		}
	}

	/**
	 * Emit an event to all registered listeners
	 * @param {string} eventType - The event type to emit
	 * @param {Object} payload - The event payload
	 */
	function emit(eventType, payload = {}) {
		const event = {
			type: eventType,
			payload,
			timestamp: Date.now(),
			id: generateUUID()
		}

		// Add to history
		eventHistory.value.unshift(event)
		if (eventHistory.value.length > maxHistorySize.value) {
			eventHistory.value = eventHistory.value.slice(0, maxHistorySize.value)
		}

		// Notify all listeners
		if (listeners.value.has(eventType)) {
			const callbacks = listeners.value.get(eventType)
			callbacks.forEach(callback => {
				try {
					callback(event.payload, event)
				} catch (error) {
					log.error(`Error in listener for ${eventType}:`, error)
				}
			})
		}

		// Also notify wildcard listeners (listen to all events)
		if (listeners.value.has('*')) {
			const callbacks = listeners.value.get('*')
			callbacks.forEach(callback => {
				try {
					callback(event.payload, event)
				} catch (error) {
					log.error('Error in wildcard listener:', error)
				}
			})
		}

		log.debug(`Event emitted: ${eventType}`, payload)
	}

	/**
	 * Emit multiple events in a batch
	 * @param {Array<{type: string, payload: Object}>} events - Array of events
	 */
	function emitBatch(events) {
		events.forEach(({ type, payload }) => emit(type, payload))
	}

	// ========================================================================
	// SETTINGS CHANGE TRACKING
	// ========================================================================

	/**
	 * Track settings snapshot for change detection
	 * @param {Object} settings - Current settings object
	 */
	function updateSettingsSnapshot(settings) {
		lastSettingsSnapshot.value = { ...settings }
	}

	/**
	 * Detect and emit settings change events
	 * @param {Object} newSettings - New settings object
	 * @param {Object} oldSettings - Old settings object (optional)
	 */
	function detectSettingsChanges(newSettings, oldSettings = null) {
		const old = oldSettings || lastSettingsSnapshot.value
		if (!old) {
			// First time, just store snapshot
			updateSettingsSnapshot(newSettings)
			return
		}

		const changes = {}
		const events = []

		// Detect all changes
		for (const key in newSettings) {
			if (newSettings[key] !== old[key]) {
				changes[key] = {
					old: old[key],
					new: newSettings[key]
				}
			}
		}

		// If no changes, return early
		if (Object.keys(changes).length === 0) {
			return
		}

		// Categorize changes and emit specific events

		// Warehouse change
		if ('warehouse' in changes) {
			events.push({
				type: 'settings:warehouse-changed',
				payload: {
					oldWarehouse: changes.warehouse.old,
					newWarehouse: changes.warehouse.new,
					requiresStockRefresh: true
				}
			})
		}

		// Stock policy changes
		const stockPolicyFields = ['allow_negative_stock']
		const stockPolicyChanges = stockPolicyFields.filter(field => field in changes)
		if (stockPolicyChanges.length > 0) {
			events.push({
				type: 'settings:stock-policy-changed',
				payload: {
					changes: stockPolicyChanges.reduce((acc, field) => {
						acc[field] = changes[field]
						return acc
					}, {}),
					requiresReload: true // Critical change
				}
			})

			// Mark for reload
			pendingReloads.value.add('stock-policy')
		}

		// Pricing/discount changes
		const pricingFields = [
			'max_discount_allowed',
			'use_percentage_discount',
			'allow_user_to_edit_additional_discount',
			'allow_user_to_edit_item_discount',
			'allow_user_to_edit_rate',
			'disable_rounded_total',
			'tax_inclusive'
		]
		const pricingChanges = pricingFields.filter(field => field in changes)
		if (pricingChanges.length > 0) {
			events.push({
				type: 'settings:pricing-changed',
				payload: {
					changes: pricingChanges.reduce((acc, field) => {
						acc[field] = changes[field]
						return acc
					}, {})
				}
			})
		}

		// Sales operations changes
		const salesFields = [
			'allow_credit_sale',
			'allow_return',
			'allow_write_off_change',
			'allow_partial_payment',
			'silent_print'
		]
		const salesChanges = salesFields.filter(field => field in changes)
		if (salesChanges.length > 0) {
			events.push({
				type: 'settings:sales-operations-changed',
				payload: {
					changes: salesChanges.reduce((acc, field) => {
						acc[field] = changes[field]
						return acc
					}, {})
				}
			})
		}

		// Display settings changes
		const displayFields = [
			'default_card_view',
			'display_item_code',
			'show_customer_balance',
			'hide_expected_amount',
			'display_discount_percentage',
			'display_discount_amount'
		]
		const displayChanges = displayFields.filter(field => field in changes)
		if (displayChanges.length > 0) {
			events.push({
				type: 'settings:display-changed',
				payload: {
					changes: displayChanges.reduce((acc, field) => {
						acc[field] = changes[field]
						return acc
					}, {})
				}
			})
		}

		// Generic settings changed event (always emitted)
		events.push({
			type: 'settings:changed',
			payload: {
				changes,
				allChanges: changes,
				timestamp: Date.now()
			}
		})

		// Emit all events
		emitBatch(events)

		// Update snapshot
		updateSettingsSnapshot(newSettings)

		log.info(`Settings changes detected: ${Object.keys(changes).join(', ')}`)
	}

	// ========================================================================
	// RELOAD MANAGEMENT
	// ========================================================================

	/**
	 * Check if a reload is pending for a specific reason
	 * @param {string} reason - The reload reason
	 * @returns {boolean}
	 */
	function isReloadPending(reason) {
		return pendingReloads.value.has(reason)
	}

	/**
	 * Mark a reload as completed
	 * @param {string} reason - The reload reason
	 */
	function markReloadCompleted(reason) {
		pendingReloads.value.delete(reason)
	}

	/**
	 * Clear all pending reloads
	 */
	function clearPendingReloads() {
		pendingReloads.value.clear()
	}

	// ========================================================================
	// BACKGROUND SYNC EVENTS
	// ========================================================================

	/**
	 * Emit stock sync configuration change
	 * @param {Object} config - Sync configuration
	 */
	function emitStockSyncConfigured(config) {
		emit('settings:sync-configured', {
			enabled: config.enabled,
			intervalMs: config.intervalMs,
			timestamp: Date.now()
		})
	}

	/**
	 * Emit stock sync status update
	 * @param {Object} status - Sync status
	 */
	function emitStockSyncStatus(status) {
		emit('sync:stock-updated', {
			...status,
			timestamp: Date.now()
		})
	}

	// ========================================================================
	// UTILITY METHODS
	// ========================================================================

	/**
	 * Clear event history
	 */
	function clearHistory() {
		eventHistory.value = []
		log.info('Event history cleared')
	}

	/**
	 * Get events by type
	 * @param {string} eventType - The event type to filter
	 * @returns {Array} - Filtered events
	 */
	function getEventsByType(eventType) {
		return eventHistory.value.filter(event => event.type === eventType)
	}

	/**
	 * Get listener count for an event type
	 * @param {string} eventType - The event type
	 * @returns {number} - Number of listeners
	 */
	function getListenerCount(eventType) {
		return listeners.value.get(eventType)?.size || 0
	}

	/**
	 * Remove all listeners
	 */
	function removeAllListeners() {
		listeners.value.clear()
		log.info('All listeners removed')
	}

	return {
		// State
		eventHistory,
		recentEvents,
		hasPendingReloads,

		// Core event system
		on,
		off,
		emit,
		emitBatch,

		// Settings change tracking
		updateSettingsSnapshot,
		detectSettingsChanges,

		// Reload management
		isReloadPending,
		markReloadCompleted,
		clearPendingReloads,

		// Background sync events
		emitStockSyncConfigured,
		emitStockSyncStatus,

		// Utility
		clearHistory,
		getEventsByType,
		getListenerCount,
		removeAllListeners,
	}
})
