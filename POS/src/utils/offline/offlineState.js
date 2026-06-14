/**
 * Enterprise-Grade Offline State Manager
 *
 * Features:
 * - Multi-signal detection (browser API + server ping + Network Info API)
 * - Stability buffer (prevents flapping between online/offline)
 * - Adaptive polling intervals
 * - Exponential backoff with jitter
 * - Connection quality tracking
 * - Tab visibility awareness
 * - Cross-tab synchronization via BroadcastChannel
 * - Captive portal detection
 *
 * @module utils/offline/offlineState
 */

import { logger } from '../logger'

const log = logger.create('OfflineState')

// ============================================================================
// CONFIGURATION
// ============================================================================

const CONFIG = {
	// Ping settings
	PING_URL: '/api/method/pos_next.api.ping',
	PING_TIMEOUT_MS: 5000,
	PING_RETRY_COUNT: 2,

	// Stability buffer - prevents flapping
	OFFLINE_THRESHOLD: 2,      // Consecutive failures before going offline
	ONLINE_THRESHOLD: 2,       // Consecutive successes before going online

	// Adaptive intervals
	INTERVAL_ONLINE_MS: 30000,      // 30s when stable online
	INTERVAL_OFFLINE_MS: 10000,     // 10s when offline (try to recover faster)
	INTERVAL_UNSTABLE_MS: 5000,     // 5s when connection is unstable
	INTERVAL_HIDDEN_MS: 60000,      // 60s when tab is hidden

	// Backoff settings
	BACKOFF_BASE_MS: 1000,
	BACKOFF_MAX_MS: 30000,
	BACKOFF_JITTER: 0.3,     // 30% jitter to prevent thundering herd

	// Quality tracking
	LATENCY_HISTORY_SIZE: 10,
	QUALITY_POOR_THRESHOLD_MS: 2000,
	QUALITY_DEGRADED_THRESHOLD_MS: 1000,

	// Debounce
	DEBOUNCE_DELAY_MS: 150,

	// Cross-tab sync
	BROADCAST_CHANNEL_NAME: 'pos_next_offline_state',
}

// ============================================================================
// NETWORK MONITOR CLASS
// ============================================================================

class NetworkMonitor {
	constructor() {
		this._isMonitoring = false
		this._pingIntervalId = null
		this._consecutiveFailures = 0
		this._consecutiveSuccesses = 0
		this._latencyHistory = []
		this._lastPingTime = 0
		this._backoffMultiplier = 1
		this._tabVisible = true
		this._broadcastChannel = null
	}

	/**
	 * Start monitoring network connectivity
	 */
	start() {
		if (this._isMonitoring) return

		this._isMonitoring = true
		this._initBroadcastChannel()
		this._initVisibilityListener()

		// Initial ping
		this._performPing()

		// Start adaptive interval
		this._scheduleNextPing()

		log.info('Network monitor started')
	}

	/**
	 * Stop monitoring
	 */
	stop() {
		this._isMonitoring = false

		if (this._pingIntervalId) {
			clearTimeout(this._pingIntervalId)
			this._pingIntervalId = null
		}

		if (this._broadcastChannel) {
			this._broadcastChannel.close()
			this._broadcastChannel = null
		}

		log.info('Network monitor stopped')
	}

	/**
	 * Initialize BroadcastChannel for cross-tab sync
	 */
	_initBroadcastChannel() {
		if (typeof BroadcastChannel === 'undefined') return

		try {
			this._broadcastChannel = new BroadcastChannel(CONFIG.BROADCAST_CHANNEL_NAME)
			this._broadcastChannel.onmessage = (event) => {
				const { type, state } = event.data
				if (type === 'STATE_SYNC') {
					// Another tab detected state change, update our state
					log.debug('Received cross-tab state sync', state)
					offlineState._handleCrossTabSync(state)
				}
			}
		} catch (error) {
			log.warn('BroadcastChannel not available', error)
		}
	}

	/**
	 * Broadcast state to other tabs
	 */
	_broadcastState(state) {
		if (this._broadcastChannel) {
			try {
				this._broadcastChannel.postMessage({ type: 'STATE_SYNC', state })
			} catch (error) {
				// Channel might be closed
			}
		}
	}

	/**
	 * Initialize tab visibility listener
	 */
	_initVisibilityListener() {
		if (typeof document === 'undefined') return

		document.addEventListener('visibilitychange', () => {
			this._tabVisible = document.visibilityState === 'visible'

			if (this._tabVisible) {
				// Tab became visible - do immediate ping
				log.debug('Tab visible, performing immediate ping')
				this._performPing()
			}

			// Reschedule with appropriate interval
			this._scheduleNextPing()
		}, { passive: true })
	}

	/**
	 * Calculate next ping interval based on state
	 */
	_getNextInterval() {
		// Slower when tab is hidden
		if (!this._tabVisible) {
			return CONFIG.INTERVAL_HIDDEN_MS
		}

		// If we're in an unstable state (transitioning), check more frequently
		if (this._consecutiveFailures > 0 && this._consecutiveFailures < CONFIG.OFFLINE_THRESHOLD) {
			return CONFIG.INTERVAL_UNSTABLE_MS
		}

		if (this._consecutiveSuccesses > 0 && this._consecutiveSuccesses < CONFIG.ONLINE_THRESHOLD) {
			return CONFIG.INTERVAL_UNSTABLE_MS
		}

		// Stable offline - try to recover with backoff
		if (offlineState._serverOnline === false) {
			const backoffInterval = Math.min(
				CONFIG.INTERVAL_OFFLINE_MS * this._backoffMultiplier,
				CONFIG.BACKOFF_MAX_MS
			)
			// Add jitter
			const jitter = 1 + (Math.random() - 0.5) * 2 * CONFIG.BACKOFF_JITTER
			return Math.floor(backoffInterval * jitter)
		}

		// Stable online
		return CONFIG.INTERVAL_ONLINE_MS
	}

	/**
	 * Schedule next ping with adaptive interval
	 */
	_scheduleNextPing() {
		if (!this._isMonitoring) return

		if (this._pingIntervalId) {
			clearTimeout(this._pingIntervalId)
		}

		const interval = this._getNextInterval()
		this._pingIntervalId = setTimeout(() => this._performPing(), interval)
	}

	/**
	 * Perform server ping with retry logic
	 */
	async _performPing() {
		if (!this._isMonitoring) return

		// Skip if manual offline mode
		if (offlineState._manualOffline) {
			this._scheduleNextPing()
			return
		}

		const startTime = performance.now()
		let success = false
		let latency = 0

		// Try ping with retries
		for (let attempt = 1; attempt <= CONFIG.PING_RETRY_COUNT; attempt++) {
			try {
				const controller = new AbortController()
				const timeoutId = setTimeout(() => controller.abort(), CONFIG.PING_TIMEOUT_MS)

				const response = await fetch(CONFIG.PING_URL, {
					method: 'GET',
					signal: controller.signal,
					cache: 'no-store',
					headers: {
						'Cache-Control': 'no-cache',
					},
				})

				clearTimeout(timeoutId)
				latency = Math.round(performance.now() - startTime)

				if (response.ok) {
					// Verify it's not a captive portal (check response content)
					const text = await response.text()
					if (text.includes('"message"') || text.includes('pong') || text.length < 100) {
						success = true
						break
					} else {
						// Possible captive portal
						log.warn('Possible captive portal detected')
					}
				}
			} catch (error) {
				if (error.name === 'AbortError') {
					log.debug(`Ping timeout (attempt ${attempt})`)
				} else {
					log.debug(`Ping failed (attempt ${attempt})`, error.message)
				}

				// Small delay before retry
				if (attempt < CONFIG.PING_RETRY_COUNT) {
					await new Promise(r => setTimeout(r, 500 * attempt))
				}
			}
		}

		// Update latency history
		if (success) {
			this._latencyHistory.push(latency)
			if (this._latencyHistory.length > CONFIG.LATENCY_HISTORY_SIZE) {
				this._latencyHistory.shift()
			}
		}

		// Update counters
		if (success) {
			this._consecutiveFailures = 0
			this._consecutiveSuccesses++
			this._backoffMultiplier = 1 // Reset backoff on success

			// Check if we've reached online threshold
			if (this._consecutiveSuccesses >= CONFIG.ONLINE_THRESHOLD) {
				if (!offlineState._serverOnline) {
					log.info(`Server online (${CONFIG.ONLINE_THRESHOLD} consecutive successes, latency: ${latency}ms)`)
					offlineState.setServerOnline(true)
					this._broadcastState(offlineState.getState())
				}
			}
		} else {
			this._consecutiveSuccesses = 0
			this._consecutiveFailures++

			// Check if we've reached offline threshold
			if (this._consecutiveFailures >= CONFIG.OFFLINE_THRESHOLD) {
				if (offlineState._serverOnline) {
					log.warn(`Server offline (${CONFIG.OFFLINE_THRESHOLD} consecutive failures)`)
					offlineState.setServerOnline(false)
					this._broadcastState(offlineState.getState())
				}
				// Increase backoff
				this._backoffMultiplier = Math.min(this._backoffMultiplier * 1.5, 10)
			}
		}

		this._lastPingTime = Date.now()
		this._scheduleNextPing()
	}

	/**
	 * Force immediate connectivity check
	 */
	async checkNow() {
		if (this._pingIntervalId) {
			clearTimeout(this._pingIntervalId)
		}
		await this._performPing()
	}

	/**
	 * Get connection quality metrics
	 */
	getQuality() {
		if (this._latencyHistory.length === 0) {
			return { quality: 'unknown', avgLatency: 0, successRate: 0 }
		}

		const avgLatency = Math.round(
			this._latencyHistory.reduce((a, b) => a + b, 0) / this._latencyHistory.length
		)

		let quality = 'good'
		if (avgLatency > CONFIG.QUALITY_POOR_THRESHOLD_MS) {
			quality = 'poor'
		} else if (avgLatency > CONFIG.QUALITY_DEGRADED_THRESHOLD_MS) {
			quality = 'degraded'
		}

		return {
			quality,
			avgLatency,
			latencyHistory: [...this._latencyHistory],
			consecutiveSuccesses: this._consecutiveSuccesses,
			consecutiveFailures: this._consecutiveFailures,
		}
	}
}

// ============================================================================
// OFFLINE STATE MANAGER CLASS
// ============================================================================

class OfflineStateManager {
	constructor() {
		// Core state
		this._manualOffline = false
		this._serverOnline = true
		this._browserOnline = typeof navigator !== 'undefined' ? navigator.onLine : true
		this._initialized = false

		// Listeners for state changes
		this._listeners = new Set()

		// Debounce timer for rapid changes
		this._debounceTimer = null

		// Pending state during debounce
		this._pendingState = null

		// Network monitor instance
		this._networkMonitor = new NetworkMonitor()

		// Previous state for transition detection
		this._previousIsOffline = false

		// Initialize browser event listeners
		if (typeof window !== 'undefined') {
			this._initBrowserListeners()
		}
	}

	/**
	 * Initialize browser online/offline event listeners
	 */
	_initBrowserListeners() {
		window.addEventListener('online', () => {
			log.debug('Browser online event')
			this._browserOnline = true

			// Browser came online - trigger immediate server check
			this._networkMonitor.checkNow()
			this._notifyChange('browser')
		}, { passive: true })

		window.addEventListener('offline', () => {
			log.debug('Browser offline event')
			this._browserOnline = false
			this._notifyChange('browser')
		}, { passive: true })

		// Also listen for network information changes (if available)
		if ('connection' in navigator) {
			const connection = navigator.connection
			connection.addEventListener('change', () => {
				log.debug('Network connection changed', {
					effectiveType: connection.effectiveType,
					downlink: connection.downlink,
				})
				// Connection changed - trigger immediate check
				this._networkMonitor.checkNow()
			}, { passive: true })
		}
	}

	/**
	 * Handle state sync from another tab
	 */
	_handleCrossTabSync(state) {
		let changed = false

		if (state.serverOnline !== undefined && this._serverOnline !== state.serverOnline) {
			this._serverOnline = state.serverOnline
			changed = true
		}

		if (changed) {
			this._notifyChange('cross-tab')
		}
	}

	/**
	 * Sync state to window variables for backward compatibility
	 */
	_syncToWindow() {
		if (typeof window === 'undefined') return

		window.posNextManualOffline = this._manualOffline
		window.posNextServerOnline = this._serverOnline
	}

	/**
	 * Notify listeners of state change with debouncing
	 */
	_notifyChange(source = 'unknown') {
		const currentIsOffline = this.isOffline
		const newState = {
			isOffline: currentIsOffline,
			manualOffline: this._manualOffline,
			serverOnline: this._serverOnline,
			browserOnline: this._browserOnline,
			source,
			transition: this._previousIsOffline !== currentIsOffline
				? (currentIsOffline ? 'went-offline' : 'went-online')
				: null,
			quality: this._networkMonitor.getQuality(),
		}

		// Store pending state
		this._pendingState = newState

		// Clear existing timer
		if (this._debounceTimer) {
			clearTimeout(this._debounceTimer)
		}

		// Debounce rapid changes
		this._debounceTimer = setTimeout(() => {
			this._debounceTimer = null

			if (this._pendingState) {
				const state = this._pendingState
				this._pendingState = null

				// Sync to window
				this._syncToWindow()

				// Update previous state for transition detection
				this._previousIsOffline = state.isOffline

				// Notify all listeners
				for (const listener of this._listeners) {
					try {
						listener(state)
					} catch (error) {
						log.error('Error in offline state listener', error)
					}
				}

				// Dispatch DOM event for components
				if (typeof window !== 'undefined') {
					window.dispatchEvent(new CustomEvent('offlineStateChange', { detail: state }))
				}

				if (state.transition) {
					log.info(`Connection ${state.transition}`, state)
				}
			}
		}, CONFIG.DEBOUNCE_DELAY_MS)
	}

	/**
	 * Get current offline status
	 */
	get isOffline() {
		return this._manualOffline || !this._browserOnline || !this._serverOnline
	}

	/**
	 * Get manual offline state
	 */
	get manualOffline() {
		return this._manualOffline
	}

	/**
	 * Get server online state
	 */
	get serverOnline() {
		return this._serverOnline
	}

	/**
	 * Get browser online state
	 */
	get browserOnline() {
		return this._browserOnline
	}

	/**
	 * Set manual offline mode
	 */
	setManualOffline(value, { silent = false } = {}) {
		const newValue = !!value
		if (this._manualOffline === newValue) return

		this._manualOffline = newValue
		log.info(`Manual offline mode ${newValue ? 'enabled' : 'disabled'}`)

		if (!silent) {
			this._notifyChange('manual')
		} else {
			this._syncToWindow()
		}
	}

	/**
	 * Toggle manual offline mode
	 */
	toggleManualOffline() {
		this.setManualOffline(!this._manualOffline)
		return this._manualOffline
	}

	/**
	 * Update server online status
	 */
	setServerOnline(isOnline, { silent = false } = {}) {
		const newValue = !!isOnline
		if (this._serverOnline === newValue) return

		this._serverOnline = newValue

		if (!silent) {
			this._notifyChange('server')
		} else {
			this._syncToWindow()
		}
	}

	/**
	 * Batch update state (for worker sync)
	 */
	updateState({ serverOnline, manualOffline } = {}) {
		let changed = false

		if (serverOnline !== undefined && this._serverOnline !== serverOnline) {
			this._serverOnline = serverOnline
			changed = true
		}

		if (manualOffline !== undefined && this._manualOffline !== manualOffline) {
			this._manualOffline = manualOffline
			changed = true
		}

		if (changed) {
			this._notifyChange('batch')
		}
	}

	/**
	 * Subscribe to state changes
	 */
	subscribe(listener) {
		if (typeof listener !== 'function') {
			throw new Error('Listener must be a function')
		}

		this._listeners.add(listener)

		// Return unsubscribe function
		return () => {
			this._listeners.delete(listener)
		}
	}

	/**
	 * Get current state snapshot
	 */
	getState() {
		return {
			isOffline: this.isOffline,
			manualOffline: this._manualOffline,
			serverOnline: this._serverOnline,
			browserOnline: this._browserOnline,
			quality: this._networkMonitor.getQuality(),
		}
	}

	/**
	 * Initialize state and start network monitoring
	 */
	initialize(initialState = {}) {
		if (this._initialized) return

		const { serverOnline = true, manualOffline = false } = initialState

		this._serverOnline = serverOnline
		this._manualOffline = manualOffline
		this._initialized = true
		this._previousIsOffline = this.isOffline

		this._syncToWindow()

		// Start network monitoring
		this._networkMonitor.start()

		log.info('Offline state initialized', this.getState())
	}

	/**
	 * Force immediate connectivity check
	 */
	async checkConnectivity() {
		await this._networkMonitor.checkNow()
		return this.getState()
	}

	/**
	 * Get connection quality metrics
	 */
	getConnectionQuality() {
		return this._networkMonitor.getQuality()
	}

	/**
	 * Reset state to defaults
	 */
	reset() {
		this._manualOffline = false
		this._serverOnline = true
		this._syncToWindow()
		this._notifyChange('reset')
	}

	/**
	 * Cleanup resources
	 */
	destroy() {
		this._networkMonitor.stop()
		this._listeners.clear()
		if (this._debounceTimer) {
			clearTimeout(this._debounceTimer)
		}
	}
}

// ============================================================================
// SINGLETON INSTANCE & EXPORTS
// ============================================================================

// Create singleton instance
export const offlineState = new OfflineStateManager()

// Legacy compatibility - isOffline function
export function isOffline() {
	return offlineState.isOffline
}

// Export convenience functions
export const setManualOffline = (value) => offlineState.setManualOffline(value)
export const toggleManualOffline = () => offlineState.toggleManualOffline()
export const getOfflineState = () => offlineState.getState()
export const checkConnectivity = () => offlineState.checkConnectivity()
export const getConnectionQuality = () => offlineState.getConnectionQuality()

// Auto-initialize when module loads (if in browser context)
if (typeof window !== 'undefined') {
	// Defer initialization to after DOM is ready
	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', () => {
			offlineState.initialize()
		})
	} else {
		// DOM already ready, initialize immediately
		setTimeout(() => offlineState.initialize(), 0)
	}
}
