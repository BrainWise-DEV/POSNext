/**
 * POS Events Composable
 *
 * Provides convenient access to the POS events system with automatic cleanup
 *
 * @example
 * ```js
 * import { usePOSEvents } from '@/composables/usePOSEvents'
 *
 * const { on, emit, onSettingsChanged, onWarehouseChanged } = usePOSEvents()
 *
 * // Listen to specific event
 * onSettingsChanged((payload) => {
 *   console.log('Settings changed:', payload.changes)
 * })
 *
 * // Listen to warehouse change
 * onWarehouseChanged(({ newWarehouse, oldWarehouse }) => {
 *   console.log(`Warehouse changed from ${oldWarehouse} to ${newWarehouse}`)
 *   // Trigger stock refresh
 * })
 * ```
 */

import { onUnmounted } from 'vue'
import { usePOSEventsStore } from '@/stores/posEvents'

export function usePOSEvents() {
	const eventsStore = usePOSEventsStore()
	const unsubscribers = []

	/**
	 * Register event listener with automatic cleanup on component unmount
	 * @param {string} eventType - Event type to listen for
	 * @param {Function} callback - Callback function
	 * @returns {Function} - Manual unsubscribe function
	 */
	function on(eventType, callback) {
		const unsubscribe = eventsStore.on(eventType, callback)
		unsubscribers.push(unsubscribe)
		return unsubscribe
	}

	/**
	 * Emit an event
	 * @param {string} eventType - Event type
	 * @param {Object} payload - Event payload
	 */
	function emit(eventType, payload) {
		eventsStore.emit(eventType, payload)
	}

	// ========================================================================
	// CONVENIENCE METHODS FOR COMMON EVENTS
	// ========================================================================

	/**
	 * Listen to all settings changes
	 * @param {Function} callback - Callback(payload, event)
	 * @returns {Function} - Unsubscribe function
	 */
	function onSettingsChanged(callback) {
		return on('settings:changed', callback)
	}

	/**
	 * Listen to warehouse changes
	 * @param {Function} callback - Callback({ oldWarehouse, newWarehouse, requiresStockRefresh })
	 * @returns {Function} - Unsubscribe function
	 */
	function onWarehouseChanged(callback) {
		return on('settings:warehouse-changed', callback)
	}

	/**
	 * Listen to stock policy changes (allow_negative_stock, etc.)
	 * @param {Function} callback - Callback({ changes, requiresReload })
	 * @returns {Function} - Unsubscribe function
	 */
	function onStockPolicyChanged(callback) {
		return on('settings:stock-policy-changed', callback)
	}

	/**
	 * Listen to pricing/discount setting changes
	 * @param {Function} callback - Callback({ changes })
	 * @returns {Function} - Unsubscribe function
	 */
	function onPricingChanged(callback) {
		return on('settings:pricing-changed', callback)
	}

	/**
	 * Listen to sales operations setting changes
	 * @param {Function} callback - Callback({ changes })
	 * @returns {Function} - Unsubscribe function
	 */
	function onSalesOperationsChanged(callback) {
		return on('settings:sales-operations-changed', callback)
	}

	/**
	 * Listen to display setting changes
	 * @param {Function} callback - Callback({ changes })
	 * @returns {Function} - Unsubscribe function
	 */
	function onDisplayChanged(callback) {
		return on('settings:display-changed', callback)
	}

	/**
	 * Listen to stock sync configuration changes
	 * @param {Function} callback - Callback({ enabled, intervalMs })
	 * @returns {Function} - Unsubscribe function
	 */
	function onStockSyncConfigured(callback) {
		return on('settings:sync-configured', callback)
	}

	/**
	 * Listen to stock sync updates
	 * @param {Function} callback - Callback(status)
	 * @returns {Function} - Unsubscribe function
	 */
	function onStockSyncUpdate(callback) {
		return on('sync:stock-updated', callback)
	}

	/**
	 * Listen to all events (wildcard)
	 * @param {Function} callback - Callback(payload, event)
	 * @returns {Function} - Unsubscribe function
	 */
	function onAny(callback) {
		return on('*', callback)
	}

	// ========================================================================
	// SETTINGS DETECTION
	// ========================================================================

	/**
	 * Detect and emit settings changes
	 * @param {Object} newSettings - New settings
	 * @param {Object} oldSettings - Old settings (optional)
	 */
	function detectSettingsChanges(newSettings, oldSettings) {
		eventsStore.detectSettingsChanges(newSettings, oldSettings)
	}

	/**
	 * Update settings snapshot for change detection
	 * @param {Object} settings - Current settings
	 */
	function updateSettingsSnapshot(settings) {
		eventsStore.updateSettingsSnapshot(settings)
	}

	// ========================================================================
	// STOCK SYNC HELPERS
	// ========================================================================

	/**
	 * Emit stock sync configured event
	 * @param {Object} config - Sync config
	 */
	function emitStockSyncConfigured(config) {
		eventsStore.emitStockSyncConfigured(config)
	}

	/**
	 * Emit stock sync status update
	 * @param {Object} status - Sync status
	 */
	function emitStockSyncStatus(status) {
		eventsStore.emitStockSyncStatus(status)
	}

	// ========================================================================
	// UTILITIES
	// ========================================================================

	/**
	 * Get recent events
	 * @returns {Array} - Recent events
	 */
	function getRecentEvents() {
		return eventsStore.recentEvents
	}

	/**
	 * Get events by type
	 * @param {string} eventType - Event type
	 * @returns {Array} - Filtered events
	 */
	function getEventsByType(eventType) {
		return eventsStore.getEventsByType(eventType)
	}

	/**
	 * Clear event history
	 */
	function clearHistory() {
		eventsStore.clearHistory()
	}

	/**
	 * Manually unsubscribe all listeners registered by this composable instance
	 */
	function unsubscribeAll() {
		unsubscribers.forEach(unsub => unsub())
		unsubscribers.length = 0
	}

	// Auto-cleanup on component unmount
	onUnmounted(() => {
		unsubscribeAll()
	})

	return {
		// Core API
		on,
		emit,

		// Convenience methods
		onSettingsChanged,
		onWarehouseChanged,
		onStockPolicyChanged,
		onPricingChanged,
		onSalesOperationsChanged,
		onDisplayChanged,
		onStockSyncConfigured,
		onStockSyncUpdate,
		onAny,

		// Settings detection
		detectSettingsChanges,
		updateSettingsSnapshot,

		// Stock sync
		emitStockSyncConfigured,
		emitStockSyncStatus,

		// Utilities
		getRecentEvents,
		getEventsByType,
		clearHistory,
		unsubscribeAll,

		// Store access (for advanced use)
		store: eventsStore,
	}
}
