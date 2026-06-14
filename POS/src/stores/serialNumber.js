/**
 * Serial Number Store - Cached Serial Number Management
 *
 * This store caches serial numbers per item to avoid reloading
 * every time the dialog opens. Cache is invalidated when:
 * - Warehouse changes
 * - Item is sold (serial consumed)
 * - Manual refresh requested
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { call } from '@/utils/apiWrapper'
import { logger } from '@/utils/logger'

const log = logger.create('SerialNumber')

export const useSerialNumberStore = defineStore('serialNumber', () => {
	// ========================================================================
	// STATE
	// ========================================================================

	// Cache: item_code -> { serials: [], warehouse, timestamp }
	const cache = ref(new Map())
	const loading = ref(false)
	const currentWarehouse = ref(null)

	// Cache TTL: 5 minutes (serials don't change often)
	const CACHE_TTL = 5 * 60 * 1000

	// ========================================================================
	// GETTERS
	// ========================================================================

	const getSerials = (itemCode) => {
		const cached = cache.value.get(itemCode)
		if (!cached) return []
		return cached.serials
	}

	const isCacheValid = (itemCode) => {
		const cached = cache.value.get(itemCode)
		if (!cached) return false

		// Check warehouse match
		if (cached.warehouse !== currentWarehouse.value) return false

		// Check TTL
		if (Date.now() - cached.timestamp > CACHE_TTL) return false

		return true
	}

	// ========================================================================
	// ACTIONS
	// ========================================================================

	/**
	 * Set current warehouse - invalidates cache if changed
	 */
	const setWarehouse = (warehouse) => {
		if (currentWarehouse.value !== warehouse) {
			currentWarehouse.value = warehouse
			// Clear cache when warehouse changes
			cache.value.clear()
			log.info(`Warehouse changed to ${warehouse}, cache cleared`)
		}
	}

	/**
	 * Fetch serial numbers for an item
	 * Uses cache if valid, otherwise fetches from server
	 */
	const fetchSerials = async (itemCode, forceRefresh = false) => {
		if (!itemCode || !currentWarehouse.value) {
			log.warn('Missing itemCode or warehouse')
			return []
		}

		// Return cached if valid and not forcing refresh
		if (!forceRefresh && isCacheValid(itemCode)) {
			log.info(`Using cached serials for ${itemCode}`)
			return getSerials(itemCode)
		}

		loading.value = true

		try {
			const response = await call('frappe.client.get_list', {
				doctype: 'Serial No',
				filters: {
					item_code: itemCode,
					warehouse: currentWarehouse.value,
					status: 'Active',
				},
				fields: ['name as serial_no', 'warehouse'],
				limit_page_length: 500,
			})

			const serials = response || []

			// Update cache
			cache.value.set(itemCode, {
				serials,
				warehouse: currentWarehouse.value,
				timestamp: Date.now(),
			})

			log.success(`Loaded ${serials.length} serials for ${itemCode}`)
			return serials
		} catch (error) {
			log.error(`Failed to fetch serials for ${itemCode}`, error)
			return []
		} finally {
			loading.value = false
		}
	}

	/**
	 * Remove consumed serials from cache (when added to cart)
	 */
	const consumeSerials = (itemCode, serialNumbers) => {
		const cached = cache.value.get(itemCode)
		if (!cached) return

		const serialsToRemove = new Set(
			Array.isArray(serialNumbers)
				? serialNumbers
				: serialNumbers.split('\n').map(s => s.trim()).filter(Boolean)
		)

		cached.serials = cached.serials.filter(
			s => !serialsToRemove.has(s.serial_no)
		)

		log.info(`Consumed ${serialsToRemove.size} serials for ${itemCode}`)
	}

	/**
	 * Return serials back to cache (when removed from cart or quantity decreased)
	 */
	const returnSerials = (itemCode, serialNumbers) => {
		const cached = cache.value.get(itemCode)
		if (!cached) return

		const serialsToReturn = Array.isArray(serialNumbers)
			? serialNumbers
			: serialNumbers.split('\n').map(s => s.trim()).filter(Boolean)

		// Add serials back to cache (avoid duplicates)
		const existingSerialNos = new Set(cached.serials.map(s => s.serial_no))

		for (const serialNo of serialsToReturn) {
			if (!existingSerialNos.has(serialNo)) {
				cached.serials.push({
					serial_no: serialNo,
					warehouse: currentWarehouse.value
				})
			}
		}

		// Sort serials by serial_no for consistent ordering
		cached.serials.sort((a, b) => a.serial_no.localeCompare(b.serial_no, undefined, { numeric: true }))

		log.info(`Returned ${serialsToReturn.length} serials for ${itemCode}`)
	}

	/**
	 * Clear cache for specific item or all items
	 */
	const clearCache = (itemCode = null) => {
		if (itemCode) {
			cache.value.delete(itemCode)
			log.info(`Cache cleared for ${itemCode}`)
		} else {
			cache.value.clear()
			log.info('All cache cleared')
		}
	}

	/**
	 * Prefetch serials for multiple items (background loading)
	 */
	const prefetchSerials = async (itemCodes) => {
		const codesToFetch = itemCodes.filter(code => !isCacheValid(code))

		if (codesToFetch.length === 0) return

		log.info(`Prefetching serials for ${codesToFetch.length} items`)

		// Fetch in parallel with concurrency limit
		const batchSize = 3
		for (let i = 0; i < codesToFetch.length; i += batchSize) {
			const batch = codesToFetch.slice(i, i + batchSize)
			await Promise.all(batch.map(code => fetchSerials(code)))
		}
	}

	return {
		// State
		cache,
		loading,
		currentWarehouse,

		// Getters
		getSerials,
		isCacheValid,

		// Actions
		setWarehouse,
		fetchSerials,
		consumeSerials,
		returnSerials,
		clearCache,
		prefetchSerials,
	}
})
