/**
 * Performance Configuration Utility
 * Detects device capabilities and adjusts performance settings accordingly
 * - CPU cores detection
 * - Device memory detection
 * - Performance tier calculation
 * - Dynamic batch sizes and debounce times
 */

import { logger } from './logger'
const log = logger.create('PerformanceConfig')

/**
 * Device performance tier
 */
const PERFORMANCE_TIERS = {
	LOW: "low",
	MEDIUM: "medium",
	HIGH: "high",
}

/**
 * Detect device performance tier based on:
 * - CPU cores (navigator.hardwareConcurrency)
 * - Device memory (navigator.deviceMemory)
 * - User agent (mobile vs desktop)
 */
function detectPerformanceTier() {
	const cpuCores = navigator.hardwareConcurrency || 2
	const deviceMemory = navigator.deviceMemory || 4 // In GB, fallback to 4GB
	const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
		navigator.userAgent,
	)

	// Calculate performance score
	let score = 0

	// CPU cores scoring
	if (cpuCores >= 8) {
		score += 3
	} else if (cpuCores >= 4) {
		score += 2
	} else {
		score += 1
	}

	// Memory scoring
	if (deviceMemory >= 8) {
		score += 3
	} else if (deviceMemory >= 4) {
		score += 2
	} else {
		score += 1
	}

	// Mobile penalty (mobile devices typically have less sustained performance)
	if (isMobile) {
		score = Math.max(1, score - 1)
	}

	// Determine tier
	if (score >= 5) {
		return PERFORMANCE_TIERS.HIGH
	} else if (score >= 3) {
		return PERFORMANCE_TIERS.MEDIUM
	} else {
		return PERFORMANCE_TIERS.LOW
	}
}

/**
 * Get performance configuration based on device tier
 */
function getPerformanceConfig(tier) {
	const configs = {
		[PERFORMANCE_TIERS.LOW]: {
			// Search & debounce
			searchDebounce: 500, // Longer debounce for slower devices
			searchBatchSize: 100, // Smaller batches

			// Item loading
			itemsPerPage: 20,
			backgroundSyncBatchSize: 100, // Smaller sync batches
			backgroundSyncInterval: 20000, // Slower sync (20s)
			statsUpdateFrequency: 5, // Update stats every 5 batches

			// Realtime stock updates
			stockBatchDelay: 800, // Longer delay to batch more updates
			stockMaxBatchSize: 50, // Smaller batches

			// Rendering
			lazyLoadRootMargin: "50px", // Load closer to viewport
			virtualScrollThreshold: 30, // Virtualize earlier

			// IndexedDB
			indexedDBBatchSize: 50, // Smaller DB writes
			cacheWriteDelay: 1000, // Delay cache writes more
		},
		[PERFORMANCE_TIERS.MEDIUM]: {
			// Search & debounce
			searchDebounce: 300, // Standard debounce
			searchBatchSize: 200,

			// Item loading
			itemsPerPage: 50,
			backgroundSyncBatchSize: 200, // Standard batch size
			backgroundSyncInterval: 15000, // Standard sync (15s)
			statsUpdateFrequency: 3, // Update stats every 3 batches

			// Realtime stock updates
			stockBatchDelay: 500, // Standard delay
			stockMaxBatchSize: 100,

			// Rendering
			lazyLoadRootMargin: "100px", // Standard preload
			virtualScrollThreshold: 50,

			// IndexedDB
			indexedDBBatchSize: 200,
			cacheWriteDelay: 500,
		},
		[PERFORMANCE_TIERS.HIGH]: {
			// Search & debounce
			searchDebounce: 150, // Faster response
			searchBatchSize: 300, // Larger batches

			// Item loading
			itemsPerPage: 100,
			backgroundSyncBatchSize: 300, // Larger sync batches
			backgroundSyncInterval: 10000, // Faster sync (10s)
			statsUpdateFrequency: 2, // Update stats every 2 batches

			// Realtime stock updates
			stockBatchDelay: 300, // Shorter delay
			stockMaxBatchSize: 200, // Larger batches

			// Rendering
			lazyLoadRootMargin: "200px", // Aggressive preload
			virtualScrollThreshold: 100, // Delay virtualization

			// IndexedDB
			indexedDBBatchSize: 300, // Larger DB writes
			cacheWriteDelay: 300, // Faster cache writes
		},
	}

	return configs[tier] || configs[PERFORMANCE_TIERS.MEDIUM]
}

/**
 * Performance Config Class
 * Singleton that provides device-optimized performance settings
 */
class PerformanceConfig {
	constructor() {
		// SSR Safety: Check if running in browser environment
		if (typeof window === 'undefined' || typeof navigator === 'undefined') {
			// Server-side or non-browser environment - use medium tier defaults
			this.tier = PERFORMANCE_TIERS.MEDIUM
			this.config = getPerformanceConfig(this.tier)
			this.cpuCores = 4
			this.deviceMemory = 4
			this.isMobile = false
			this.autoDetectedTier = PERFORMANCE_TIERS.MEDIUM
			log.info("SSR mode detected, using medium tier defaults")
			return
		}

		// Detect device capabilities
		this.cpuCores = navigator.hardwareConcurrency || 2
		this.deviceMemory = navigator.deviceMemory || 4
		this.isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
			navigator.userAgent,
		)

		// Auto-detect performance tier
		this.autoDetectedTier = detectPerformanceTier()

		// Check for manual override in localStorage
		const manualTier = this.getStoredTier()
		if (manualTier && PERFORMANCE_TIERS[manualTier.toUpperCase()]) {
			this.tier = manualTier
			log.info(`Using manual performance tier override: ${manualTier}`)
		} else {
			this.tier = this.autoDetectedTier
		}

		// Get configuration for the selected tier
		this.config = getPerformanceConfig(this.tier)

		// Log detected config (only in development)
		if (import.meta.env?.DEV) {
			log.debug("Performance Config Detected", {
				tier: this.tier,
				autoDetected: this.autoDetectedTier,
				manual: manualTier ? true : false,
				cpuCores: this.cpuCores,
				deviceMemory: `${this.deviceMemory}GB`,
				isMobile: this.isMobile,
				config: this.config,
			})
		}
	}

	/**
	 * Get stored tier from localStorage
	 */
	getStoredTier() {
		if (typeof window === 'undefined' || !window.localStorage) {
			return null
		}
		try {
			return localStorage.getItem('pos_performance_tier')
		} catch (error) {
			log.error('Failed to read performance tier from localStorage', error)
			return null
		}
	}

	/**
	 * Set performance tier manually (user override)
	 * @param {string} tier - Performance tier (low, medium, high)
	 */
	setTier(tier) {
		const normalizedTier = tier?.toLowerCase()

		if (!normalizedTier || !PERFORMANCE_TIERS[normalizedTier.toUpperCase()]) {
			log.error(`Invalid performance tier: ${tier}. Must be one of: low, medium, high`)
			return false
		}

		// Update tier and config
		this.tier = normalizedTier
		this.config = getPerformanceConfig(normalizedTier)

		// Save to localStorage
		if (typeof window !== 'undefined' && window.localStorage) {
			try {
				localStorage.setItem('pos_performance_tier', normalizedTier)
				log.info(`Performance tier set to: ${normalizedTier}`)
			} catch (error) {
				log.error('Failed to save performance tier to localStorage', error)
			}
		}

		// Emit custom event for reactive updates
		if (typeof window !== 'undefined') {
			window.dispatchEvent(new CustomEvent('performanceConfigChanged', {
				detail: {
					tier: normalizedTier,
					config: this.config,
					autoDetected: this.autoDetectedTier
				}
			}))
		}

		return true
	}

	/**
	 * Reset to auto-detected tier (remove manual override)
	 */
	resetTier() {
		// Remove from localStorage
		if (typeof window !== 'undefined' && window.localStorage) {
			try {
				localStorage.removeItem('pos_performance_tier')
				log.info('Removed manual performance tier override')
			} catch (error) {
				log.error('Failed to remove performance tier from localStorage', error)
			}
		}

		// Restore auto-detected tier
		this.tier = this.autoDetectedTier
		this.config = getPerformanceConfig(this.tier)

		// Emit custom event for reactive updates
		if (typeof window !== 'undefined') {
			window.dispatchEvent(new CustomEvent('performanceConfigChanged', {
				detail: {
					tier: this.tier,
					config: this.config,
					autoDetected: this.autoDetectedTier
				}
			}))
		}

		return true
	}

	/**
	 * Get current performance tier
	 */
	getTier() {
		return this.tier
	}

	/**
	 * Get auto-detected tier (before any manual override)
	 */
	getAutoDetectedTier() {
		return this.autoDetectedTier
	}

	/**
	 * Check if current tier is manually overridden
	 */
	isManualOverride() {
		return this.tier !== this.autoDetectedTier
	}

	/**
	 * Get specific config value
	 */
	get(key) {
		return this.config[key]
	}

	/**
	 * Get all config
	 */
	getAll() {
		return { ...this.config }
	}

	/**
	 * Get CPU cores
	 */
	getCPUCores() {
		return this.cpuCores
	}

	/**
	 * Get device memory in GB
	 */
	getDeviceMemory() {
		return this.deviceMemory
	}

	/**
	 * Check if device is mobile
	 */
	isMobileDevice() {
		return this.isMobile
	}

	/**
	 * Check if device is low-end
	 */
	isLowEnd() {
		return this.tier === PERFORMANCE_TIERS.LOW
	}

	/**
	 * Check if device is high-end
	 */
	isHighEnd() {
		return this.tier === PERFORMANCE_TIERS.HIGH
	}

	/**
	 * Get recommended worker count for parallel operations
	 */
	getRecommendedWorkerCount() {
		// Use 50% of available cores, min 1, max 4
		return Math.max(1, Math.min(4, Math.floor(this.cpuCores / 2)))
	}

	/**
	 * Get throttling multiplier for performance testing
	 * Returns how much to throttle based on device tier
	 */
	getThrottlingMultiplier() {
		switch (this.tier) {
			case PERFORMANCE_TIERS.HIGH:
				return 1 // No throttling needed
			case PERFORMANCE_TIERS.MEDIUM:
				return 2 // 2x throttling
			case PERFORMANCE_TIERS.LOW:
				return 4 // 4x throttling
			default:
				return 2
		}
	}

	/**
	 * Calculate dynamic batch size based on data size and device capability
	 */
	getDynamicBatchSize(dataSize, operation = "default") {
		let baseBatchSize = this.config.backgroundSyncBatchSize

		// Adjust based on operation type
		const operationMultipliers = {
			search: 0.5, // Smaller batches for search
			sync: 1.0, // Standard for sync
			cache: 1.5, // Larger for cache writes
			render: 0.3, // Smaller for rendering
		}

		const multiplier = operationMultipliers[operation] || 1.0

		// Calculate batch size
		let batchSize = Math.floor(baseBatchSize * multiplier)

		// Ensure minimum batch size
		batchSize = Math.max(10, batchSize)

		// Cap based on data size
		if (dataSize && dataSize < batchSize) {
			return dataSize
		}

		return batchSize
	}
}

/**
 * Create singleton instance with fallback error handling
 */
export const performanceConfig = (() => {
	try {
		return new PerformanceConfig()
	} catch (error) {
		log.error('Failed to initialize PerformanceConfig, using defaults', error)
		// Return a safe default config
		return {
			tier: PERFORMANCE_TIERS.MEDIUM,
			autoDetectedTier: PERFORMANCE_TIERS.MEDIUM,
			config: getPerformanceConfig(PERFORMANCE_TIERS.MEDIUM),
			cpuCores: 4,
			deviceMemory: 4,
			isMobile: false,
			getStoredTier: () => null,
			setTier: () => false,
			resetTier: () => false,
			getTier: () => PERFORMANCE_TIERS.MEDIUM,
			getAutoDetectedTier: () => PERFORMANCE_TIERS.MEDIUM,
			isManualOverride: () => false,
			get: (key) => getPerformanceConfig(PERFORMANCE_TIERS.MEDIUM)[key],
			getAll: () => ({ ...getPerformanceConfig(PERFORMANCE_TIERS.MEDIUM) }),
			getCPUCores: () => 4,
			getDeviceMemory: () => 4,
			isMobileDevice: () => false,
			isLowEnd: () => false,
			isHighEnd: () => false,
			getRecommendedWorkerCount: () => 2,
			getThrottlingMultiplier: () => 2,
			getDynamicBatchSize: (dataSize) => Math.min(dataSize || 200, 200),
		}
	}
})()

// Export tier constants for comparison
export { PERFORMANCE_TIERS }
