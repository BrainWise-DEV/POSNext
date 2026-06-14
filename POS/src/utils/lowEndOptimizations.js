/**
 * Low-End Device Optimizations
 *
 * This utility provides performance optimizations specifically for
 * low-end cashier devices with limited CPU and memory resources.
 */

import { logger } from './logger'
const log = logger.create('LowEndOptimizations')

/**
 * requestIdleCallback polyfill for browsers that don't support it
 */
const requestIdleCallback = window.requestIdleCallback || function(cb) {
	const start = Date.now()
	return setTimeout(function() {
		cb({
			didTimeout: false,
			timeRemaining: function() {
				return Math.max(0, 50 - (Date.now() - start))
			}
		})
	}, 1)
}

const cancelIdleCallback = window.cancelIdleCallback || function(id) {
	clearTimeout(id)
}

/**
 * Schedule a task to run during browser idle time
 * Perfect for non-critical operations that shouldn't block user interactions
 *
 * @param {Function} task - Function to execute during idle time
 * @param {Object} options - Options { timeout: number }
 * @returns {number} Handle to cancel the callback
 */
export function runWhenIdle(task, options = {}) {
	const { timeout = 2000 } = options

	return requestIdleCallback((deadline) => {
		// Only run if we have time remaining or we've hit the timeout
		if (deadline.timeRemaining() > 0 || deadline.didTimeout) {
			try {
				task()
			} catch (error) {
				log.error('Error in idle callback', error)
			}
		} else {
			// Reschedule if we don't have time
			runWhenIdle(task, options)
		}
	}, { timeout })
}

/**
 * Cancel a scheduled idle callback
 */
export function cancelIdleTask(handle) {
	cancelIdleCallback(handle)
}

/**
 * Debounce function with requestAnimationFrame for better performance
 * Uses RAF to ensure updates happen at optimal times
 *
 * @param {Function} func - Function to debounce
 * @param {number} wait - Milliseconds to wait
 * @returns {Function} Debounced function
 */
export function debounceRAF(func, wait = 16) {
	let timeout
	let rafId

	return function executedFunction(...args) {
		const later = () => {
			clearTimeout(timeout)

			rafId = requestAnimationFrame(() => {
				func(...args)
			})
		}

		clearTimeout(timeout)
		if (rafId) {
			cancelAnimationFrame(rafId)
		}

		timeout = setTimeout(later, wait)
	}
}

/**
 * Throttle function with requestAnimationFrame
 * Ensures function only executes once per animation frame
 *
 * @param {Function} func - Function to throttle
 * @returns {Function} Throttled function
 */
export function throttleRAF(func) {
	let rafId = null
	let lastArgs = null

	return function executedFunction(...args) {
		lastArgs = args

		if (rafId === null) {
			rafId = requestAnimationFrame(() => {
				func(...lastArgs)
				rafId = null
				lastArgs = null
			})
		}
	}
}

/**
 * Add passive event listener for better scroll performance
 * Passive listeners tell browser it's safe to scroll immediately
 *
 * @param {Element} element - DOM element
 * @param {string} event - Event name
 * @param {Function} handler - Event handler
 * @param {Object} options - Additional options
 * @returns {Function} Cleanup function
 */
export function addPassiveListener(element, event, handler, options = {}) {
	const passiveOptions = {
		passive: true,
		capture: false,
		...options
	}

	element.addEventListener(event, handler, passiveOptions)

	// Return cleanup function
	return () => {
		element.removeEventListener(event, handler, passiveOptions)
	}
}

/**
 * Batch DOM reads and writes to prevent layout thrashing
 * Collects all reads, then all writes, preventing forced reflows
 */
class DOMBatcher {
	constructor() {
		this.reads = []
		this.writes = []
		this.scheduled = false
	}

	/**
	 * Schedule a DOM read operation
	 * @param {Function} readFn - Function that reads from DOM
	 * @returns {Promise} Promise that resolves with read result
	 */
	read(readFn) {
		return new Promise((resolve) => {
			this.reads.push(() => {
				const result = readFn()
				resolve(result)
			})
			this.schedule()
		})
	}

	/**
	 * Schedule a DOM write operation
	 * @param {Function} writeFn - Function that writes to DOM
	 * @returns {Promise} Promise that resolves when write completes
	 */
	write(writeFn) {
		return new Promise((resolve) => {
			this.writes.push(() => {
				writeFn()
				resolve()
			})
			this.schedule()
		})
	}

	schedule() {
		if (this.scheduled) return

		this.scheduled = true
		requestAnimationFrame(() => {
			this.flush()
		})
	}

	flush() {
		// Execute all reads first
		const reads = this.reads.splice(0)
		reads.forEach(read => read())

		// Then execute all writes
		const writes = this.writes.splice(0)
		writes.forEach(write => write())

		this.scheduled = false
	}
}

export const domBatcher = new DOMBatcher()

/**
 * Optimize click handler for low-end devices
 * Prevents click delays and ensures immediate feedback
 *
 * @param {Function} handler - Click handler function
 * @param {Object} options - Options
 * @returns {Object} Touch and click handlers
 */
export function createOptimizedClickHandler(handler, options = {}) {
	const { feedback = true } = options

	let touchStartTime = 0
	let touchMoved = false
	let touchHandled = false
	let touchEndTime = 0
	const MOVE_THRESHOLD = 10
	const GHOST_CLICK_THRESHOLD = 500 // Time window to ignore click after touch
	let startX = 0
	let startY = 0

	const handlers = {
		touchstart: (event) => {
			touchStartTime = Date.now()
			touchMoved = false
			touchHandled = false

			const touch = event.touches[0]
			startX = touch.clientX
			startY = touch.clientY

			// Visual feedback
			if (feedback && event.currentTarget) {
				event.currentTarget.style.opacity = '0.7'
			}
		},

		touchmove: (event) => {
			const touch = event.touches[0]
			const deltaX = Math.abs(touch.clientX - startX)
			const deltaY = Math.abs(touch.clientY - startY)

			if (deltaX > MOVE_THRESHOLD || deltaY > MOVE_THRESHOLD) {
				touchMoved = true

				// Remove feedback if moved
				if (feedback && event.currentTarget) {
					event.currentTarget.style.opacity = ''
				}
			}
		},

		touchend: (event) => {
			// Remove feedback
			if (feedback && event.currentTarget) {
				event.currentTarget.style.opacity = ''
			}

			// Only trigger if touch was quick and didn't move
			const touchDuration = Date.now() - touchStartTime
			if (!touchMoved && touchDuration < 500) {
				event.preventDefault() // Prevent mouse events
				touchHandled = true
				touchEndTime = Date.now()

				// Use requestAnimationFrame for smooth execution
				requestAnimationFrame(() => {
					handler(event)
				})
			}

			touchStartTime = 0
			touchMoved = false
		},

		click: (event) => {
			// Prevent ghost clicks after touch events
			const timeSinceTouchEnd = Date.now() - touchEndTime
			if (touchHandled && timeSinceTouchEnd < GHOST_CLICK_THRESHOLD) {
				// This is a ghost click from a touch event - ignore it
				event.preventDefault()
				event.stopPropagation()
				return
			}

			// Real click from mouse or non-touch device
			requestAnimationFrame(() => {
				handler(event)
			})
		}
	}

	// Reset touchHandled flag after GHOST_CLICK_THRESHOLD
	// to prevent indefinite blocking of mouse clicks
	const resetTouchHandled = () => {
		if (touchHandled) {
			const timeSinceTouchEnd = Date.now() - touchEndTime
			if (timeSinceTouchEnd >= GHOST_CLICK_THRESHOLD) {
				touchHandled = false
			}
		}
	}
	setInterval(resetTouchHandled, GHOST_CLICK_THRESHOLD)

	return handlers
}

/**
 * Chunk large array operations to prevent blocking
 * Processes array in small chunks during idle time
 *
 * @param {Array} array - Array to process
 * @param {Function} processor - Function to process each item
 * @param {Object} options - Options
 * @returns {Promise} Promise that resolves when processing complete
 */
export async function processArrayInChunks(array, processor, options = {}) {
	const {
		chunkSize = 50,
		onProgress = null,
		signal = null
	} = options

	const total = array.length
	let processed = 0

	for (let i = 0; i < total; i += chunkSize) {
		// Check if cancelled
		if (signal?.aborted) {
			throw new Error('Processing cancelled')
		}

		// Process chunk
		const chunk = array.slice(i, i + chunkSize)
		await new Promise(resolve => {
			runWhenIdle(() => {
				chunk.forEach(item => processor(item))
				processed += chunk.length

				if (onProgress) {
					onProgress(processed, total)
				}

				resolve()
			})
		})
	}

	return processed
}

/**
 * Detect if device is low-end based on various metrics
 * @returns {boolean} True if device is low-end
 */
export function isLowEndDevice() {
	// Check hardware concurrency (CPU cores)
	const cores = navigator.hardwareConcurrency || 2
	if (cores <= 2) return true

	// Check device memory (if available)
	if (navigator.deviceMemory && navigator.deviceMemory <= 2) {
		return true
	}

	// Check connection speed
	if (navigator.connection) {
		const conn = navigator.connection
		if (conn.effectiveType === 'slow-2g' || conn.effectiveType === '2g') {
			return true
		}
		if (conn.saveData) {
			return true // User has enabled data saver
		}
	}

	return false
}

/**
 * Get recommended performance settings based on device capabilities
 * @returns {Object} Performance settings
 */
export function getPerformanceSettings() {
	const isLowEnd = isLowEndDevice()

	return {
		isLowEnd,
		itemsPerPage: isLowEnd ? 10 : 20,
		debounceDelay: isLowEnd ? 500 : 300,
		throttleDelay: isLowEnd ? 200 : 100,
		enableAnimations: !isLowEnd,
		lazyLoadThreshold: isLowEnd ? '50px' : '200px',
		maxVisibleItems: isLowEnd ? 50 : 100,
	}
}

log.info('Low-end optimizations loaded', { isLowEnd: isLowEndDevice() })
