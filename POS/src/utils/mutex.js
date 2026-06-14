/**
 * Mutex Utilities
 *
 * Provides mutex/lock implementations for preventing concurrent operations.
 *
 * @example
 * import { CoalescingMutex } from '@/utils/mutex'
 *
 * const mutex = new CoalescingMutex({ timeout: 30000 })
 *
 * // Multiple concurrent calls will be coalesced
 * await mutex.withLock(async () => {
 *   // Only one execution at a time
 *   await doExpensiveOperation()
 * })
 */

/**
 * Coalescing mutex that ensures only one operation runs at a time.
 *
 * Behavior:
 * - If no operation is running, starts one immediately
 * - If an operation is running, waits for it to complete then re-checks for pending work
 * - Prevents thundering herd by coalescing concurrent requests
 * - Includes timeout protection to prevent indefinite hangs
 *
 * Use cases:
 * - Sync operations (prevent duplicate syncs)
 * - API calls that should not run concurrently
 * - Resource initialization that should happen once
 */
export class CoalescingMutex {
	/**
	 * @param {Object} options - Configuration options
	 * @param {number} options.timeout - Timeout in milliseconds (default: 60000)
	 * @param {string} options.name - Optional name for debugging
	 */
	constructor(options = {}) {
		this._activePromise = null
		this._timeout = options.timeout ?? 60000
		this._name = options.name || "Mutex"
	}

	/**
	 * Check if the mutex is currently locked
	 * @returns {boolean}
	 */
	get isLocked() {
		return this._activePromise !== null
	}

	/**
	 * Execute function with exclusive access.
	 * If locked, waits for completion then re-executes to catch any new work.
	 *
	 * @param {Function} fn - Async function to execute
	 * @param {Function} logFn - Optional logging function for debug output
	 * @returns {Promise} Result of the function execution
	 */
	async withLock(fn, logFn = null) {
		// If already running, wait for it then run again to catch new work
		if (this._activePromise) {
			logFn?.(`${this._name}: Waiting for ongoing operation to complete...`)
			try {
				await this._activePromise
			} catch {
				// Ignore errors from the previous run, we'll do our own
			}
			// Recursive call - will either start fresh or wait again
			return this.withLock(fn, logFn)
		}

		// Create the guarded promise with timeout
		this._activePromise = this._executeWithTimeout(fn)

		try {
			return await this._activePromise
		} finally {
			this._activePromise = null
		}
	}

	/**
	 * Execute function with timeout protection
	 * @private
	 */
	async _executeWithTimeout(fn) {
		return new Promise((resolve, reject) => {
			const timeoutId = setTimeout(() => {
				reject(new Error(`${this._name}: Operation timed out after ${this._timeout}ms`))
			}, this._timeout)

			fn()
				.then((result) => {
					clearTimeout(timeoutId)
					resolve(result)
				})
				.catch((error) => {
					clearTimeout(timeoutId)
					reject(error)
				})
		})
	}
}

/**
 * Simple mutex that queues concurrent callers.
 * Unlike CoalescingMutex, each caller executes their own function in order.
 *
 * Use cases:
 * - Sequential database writes
 * - Operations where each call must execute independently
 */
export class QueuedMutex {
	/**
	 * @param {Object} options - Configuration options
	 * @param {number} options.timeout - Timeout in milliseconds (default: 60000)
	 * @param {string} options.name - Optional name for debugging
	 */
	constructor(options = {}) {
		this._queue = Promise.resolve()
		this._timeout = options.timeout ?? 60000
		this._name = options.name || "QueuedMutex"
		this._pendingCount = 0
	}

	/**
	 * Check if the mutex has pending operations
	 * @returns {boolean}
	 */
	get isLocked() {
		return this._pendingCount > 0
	}

	/**
	 * Number of operations waiting in queue
	 * @returns {number}
	 */
	get pendingCount() {
		return this._pendingCount
	}

	/**
	 * Execute function in queue order.
	 * Each caller waits for previous callers to complete.
	 *
	 * @param {Function} fn - Async function to execute
	 * @param {Function} logFn - Optional logging function
	 * @returns {Promise} Result of the function execution
	 */
	async withLock(fn, logFn = null) {
		this._pendingCount++

		if (this._pendingCount > 1) {
			logFn?.(`${this._name}: Queued (${this._pendingCount - 1} ahead)`)
		}

		// Chain onto the queue
		const result = this._queue.then(async () => {
			try {
				return await this._executeWithTimeout(fn)
			} finally {
				this._pendingCount--
			}
		})

		// Update queue to include this operation
		this._queue = result.catch(() => {})

		return result
	}

	/**
	 * Execute function with timeout protection
	 * @private
	 */
	async _executeWithTimeout(fn) {
		return new Promise((resolve, reject) => {
			const timeoutId = setTimeout(() => {
				reject(new Error(`${this._name}: Operation timed out after ${this._timeout}ms`))
			}, this._timeout)

			fn()
				.then((result) => {
					clearTimeout(timeoutId)
					resolve(result)
				})
				.catch((error) => {
					clearTimeout(timeoutId)
					reject(error)
				})
		})
	}
}
