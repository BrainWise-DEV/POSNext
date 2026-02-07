import { call } from "@/utils/apiWrapper"
import { isOffline } from "@/utils/offline"
import { offlineWorker } from "@/utils/offline/workerClient"
import { cacheItems, getCachedVariants, updateItemBatchSerialData } from "@/utils/offline/items"
import { performanceConfig } from "@/utils/performanceConfig"
import { logger } from "@/utils/logger"
import { createResource } from "frappe-ui"
import { defineStore } from "pinia"
import { computed, ref } from "vue"
import { useStockStore } from "./stock"
import { usePOSShiftStore } from "./posShift"
import { useRealtimePosProfile } from "@/composables/useRealtimePosProfile"

const log = logger.create('ItemSearch')

/**
 * Fetch and cache variants for all template items
 * This ensures variants are available for offline use
 * @param {Array} items - Items array to check for templates
 * @param {string} posProfile - POS Profile name
 */
async function cacheVariantsForTemplates(items, posProfile) {
	if (!items || items.length === 0 || !posProfile) return

	// Find template items (items with has_variants = 1)
	const templateItems = items.filter(item => item.has_variants)

	if (templateItems.length === 0) {
		log.debug("No template items found - skipping variant caching")
		return
	}

	log.info(`Caching variants for ${templateItems.length} template items`)

	// Fetch variants for each template in parallel (with concurrency limit)
	const CONCURRENCY_LIMIT = 3
	const allVariants = []

	for (let i = 0; i < templateItems.length; i += CONCURRENCY_LIMIT) {
		const batch = templateItems.slice(i, i + CONCURRENCY_LIMIT)

		const batchPromises = batch.map(async (template) => {
			try {
				const response = await call("pos_next.api.items.get_item_variants", {
					template_item: template.item_code,
					pos_profile: posProfile,
				})
				const variants = response?.message || response || []

				if (variants.length > 0) {
					log.debug(`Fetched ${variants.length} variants for ${template.item_code}`)
					return variants
				}
				return []
			} catch (error) {
				log.warn(`Failed to fetch variants for ${template.item_code}:`, error.message)
				return []
			}
		})

		const batchResults = await Promise.all(batchPromises)
		for (const variants of batchResults) {
			allVariants.push(...variants)
		}
	}

	// Cache all variants in IndexedDB
	if (allVariants.length > 0) {
		try {
			await cacheItems(allVariants)
			log.success(`Cached ${allVariants.length} variants for offline use`)
		} catch (error) {
			log.error("Failed to cache variants:", error)
		}
	}
}

/**
 * Fetch and cache batch/serial data for items with batch or serial tracking
 * This ensures batch/serial selection works offline
 * @param {Array} items - Items array to check for batch/serial items
 * @param {string} warehouse - Warehouse to fetch stock from
 */
async function cacheBatchSerialForItems(items, warehouse) {
	if (!items || items.length === 0 || !warehouse) return

	// Find items with batch or serial tracking
	const batchSerialItems = items.filter(
		item => item.has_batch_no || item.has_serial_no
	)

	if (batchSerialItems.length === 0) {
		log.debug("No batch/serial items found - skipping batch/serial caching")
		return
	}

	log.info(`Caching batch/serial data for ${batchSerialItems.length} items`)

	// Fetch in batches to avoid too large requests
	const BATCH_SIZE = 20
	const itemCodes = batchSerialItems.map(item => item.item_code)

	for (let i = 0; i < itemCodes.length; i += BATCH_SIZE) {
		const batchCodes = itemCodes.slice(i, i + BATCH_SIZE)

		try {
			const response = await call("pos_next.api.items.get_batch_serial_data_for_items", {
				item_codes: JSON.stringify(batchCodes),
				warehouse: warehouse,
			})

			const data = response?.message || response || {}

			if (Object.keys(data).length > 0) {
				await updateItemBatchSerialData(data)
				log.debug(`Cached batch/serial data for ${Object.keys(data).length} items`)
			}
		} catch (error) {
			log.warn(`Failed to fetch batch/serial data for batch ${i}:`, error.message)
		}
	}

	log.success(`Finished caching batch/serial data for offline use`)
}

export const useItemSearchStore = defineStore("itemSearch", () => {
	// Get stock store instance
	const stockStore = useStockStore()

	// Get shift store for warehouse info (for batch/serial caching)
	const shiftStore = usePOSShiftStore()

	// Real-time POS Profile updates
	const { onPosProfileUpdate } = useRealtimePosProfile()

	// State
	const allItems = ref([]) // For browsing (lazy loaded)
	const searchResults = ref([]) // For search results (cache + server)
	const searchTerm = ref("")
	const selectedItemGroup = ref(null)
	const itemGroups = ref([])
	const profileItemGroups = ref([]) // Item groups from POS Profile filter
	const loading = ref(false)
	const loadingMore = ref(false)
	const searching = ref(false) // Separate loading state for search
	const posProfile = ref(null)
	const cartItems = ref([])

	// Sorting state - for user-triggered sorting filters
	const sortBy = ref(null) // Options: 'name', 'quantity', 'item_group', null (no sorting)
	const sortOrder = ref('asc') // Options: 'asc', 'desc'

	// Lazy loading state - dynamically adjusted based on device performance
	const currentOffset = ref(0)
	const itemsPerPage = computed(() => performanceConfig.get("itemsPerPage")) // Reactive: auto-adjusted 20/50/100 based on device
	const hasMore = ref(true)
	const totalItemsLoaded = ref(0)
	const totalServerItems = ref(0) // Total items on server (for pagination)

	// Cache state
	const cacheReady = ref(false)
	const cacheSyncing = ref(false)
	const cacheStats = ref({ items: 0, lastSync: null })
	const serverDataFresh = ref(false) // Track if we have fresh server data in current session

	// Performance helpers
	const allItemsVersion = ref(0)
	const searchResultsVersion = ref(0)

	const baseResultCache = new Map()
	const itemRegistry = new Map()
	const registeredAllItems = new Set()
	const registeredSearchItems = new Set()

	// Search debounce timer
	let searchDebounceTimer = null

	// Real-time POS Profile update handler
	let posProfileUpdateCleanup = null

	// Sync cancellation token - incremented to cancel any in-flight sync
	let syncGeneration = 0

	// ========================================================================
	// SMART CACHE UPDATE HELPERS
	// ========================================================================

	/**
	 * Calculates delta between old and new item groups
	 * @param {Array<Object>} oldGroups - Previous item groups
	 * @param {Array<Object>} newGroups - New item groups
	 * @returns {Object} Delta with added and removed groups
	 */
	function calculateItemGroupDelta(oldGroups, newGroups) {
		const oldSet = new Set(oldGroups.map(g => g.item_group))
		const newSet = new Set(newGroups.map(g => g.item_group))

		return {
			added: [...newSet].filter(g => !oldSet.has(g)),
			removed: [...oldSet].filter(g => !newSet.has(g)),
			unchanged: [...newSet].filter(g => oldSet.has(g))
		}
	}

	/**
	 * Removes items from specified groups (surgical deletion)
	 * @param {Array<string>} groups - Groups to remove
	 * @returns {Promise<number>} Number of items removed
	 */
	async function removeItemsFromGroups(groups) {
		if (!groups || groups.length === 0) {
			return 0
		}

		try {
			const result = await offlineWorker.removeItemsByGroups(groups)
			const removed = result?.removed || 0

			log.success(`Removed ${removed} items from ${groups.length} group(s)`, {
				groups: groups.slice(0, 5), // Log first 5 to avoid spam
				totalGroups: groups.length
			})

			return removed
		} catch (error) {
			log.error("Failed to remove items from groups", {
				groups,
				error: error.message
			})
			throw error
		}
	}

	/**
	 * Fetches and caches items from new groups (incremental addition)
	 * Uses the standard fetchItemsFromGroups function
	 * @param {Array<string>} groups - Group names to fetch
	 * @param {string} profile - POS Profile name
	 * @returns {Promise<number>} Total items cached
	 */
	async function fetchAndCacheNewGroups(groups, profile) {
		if (!groups || groups.length === 0) {
			return 0
		}

		try {
			// Convert group names to group objects format
			const groupObjects = groups.map(g => ({ item_group: g }))

			// Reuse the standard fetch function
			const items = await fetchItemsFromGroups(profile, groupObjects)

			if (items.length > 0) {
				await offlineWorker.cacheItems(items)
				log.success(`Cached ${items.length} items from ${groups.length} group(s)`)
				return items.length
			}

			return 0
		} catch (error) {
			log.error("Failed to fetch and cache new groups", error)
			return 0
		}
	}

	/**
	 * Handles POS Profile update with smart cache strategy and recovery
	 * @param {Object} updateData - Update event data
	 * @param {string} profile - Current POS Profile
	 */
	async function handlePosProfileUpdateWithRecovery(updateData, profile) {
		// Guard: Only handle updates for our current profile
		if (updateData.pos_profile !== profile) {
			log.debug("Ignoring update for different profile", {
				received: updateData.pos_profile,
				current: profile
			})
			return
		}

		log.info(`POS Profile ${profile} updated remotely - applying smart cache update`, {
			changeType: updateData.change_type,
			timestamp: updateData.timestamp
		})

		// Calculate delta
		const delta = calculateItemGroupDelta(
			profileItemGroups.value || [],
			updateData.item_groups || []
		)

		// Update the reference immediately
		if (updateData.item_groups) {
			profileItemGroups.value = updateData.item_groups
		}

		// No changes? Early exit
		if (delta.added.length === 0 && delta.removed.length === 0) {
			log.info("No item group changes detected - skipping cache update")
			return
		}

		log.info("Item group delta calculated", {
			added: delta.added.length,
			removed: delta.removed.length,
			unchanged: delta.unchanged.length
		})

		// Attempt smart cache update
		try {
			const startTime = performance.now()

			// Phase 1: Remove obsolete items
			const removedCount = await removeItemsFromGroups(delta.removed)

			// Phase 2: Add new items
			const cachedCount = await fetchAndCacheNewGroups(delta.added, profile)

			// Phase 3: Refresh view from server (bypass stale cache)
			await loadAllItems(profile, true)

			const duration = Math.round(performance.now() - startTime)

			log.success("Smart cache update completed", {
				duration: `${duration}ms`,
				removed: removedCount,
				cached: cachedCount,
				addedGroups: delta.added.length,
				removedGroups: delta.removed.length
			})

		} catch (error) {
			log.error("Smart cache update failed - attempting recovery", {
				error: error.message,
				stack: error.stack
			})

			// Recovery Strategy: Full cache rebuild
			await attemptFullCacheRecovery(profile)
		}
	}

	/**
	 * Fallback recovery: Full cache rebuild
	 * @param {string} profile - POS Profile name
	 */
	async function attemptFullCacheRecovery(profile) {
		log.warn("Attempting full cache recovery")

		try {
			// Clear corrupted cache
			await offlineWorker.clearItemsCache()
			log.info("Cache cleared successfully")

			// Reload from server (force server fetch since cache was cleared)
			await loadAllItems(profile, true)
			log.success("Full cache recovery completed")

		} catch (recoveryError) {
			log.error("Recovery failed - manual intervention required", {
				error: recoveryError.message,
				stack: recoveryError.stack
			})

			// Last resort: Show user a message
			// TODO: Integrate with notification system
			console.error(
				"Failed to update item cache. Please refresh the page manually.",
				recoveryError
			)
		}
	}

	// Resources (for server-side operations)
	const itemGroupsResource = createResource({
		url: "pos_next.api.items.get_item_groups",
		makeParams() {
			return {
				pos_profile: posProfile.value,
			}
		},
		auto: false,
		onSuccess(data) {
			itemGroups.value = (data?.message || data || [])
		},
		onError(error) {
			log.error("Error fetching item groups", error)
			itemGroups.value = []
		},
	})

	const searchByBarcodeResource = createResource({
		url: "pos_next.api.items.search_by_barcode",
		auto: false,
	})

	// Getters
	function clearBaseCache() {
		baseResultCache.clear()
		filteredItemsCache.clear() // Also clear filtered items cache
		lastFilterKey = ''
	}

	function removeRegisteredItems(registrySet) {
		if (!registrySet || registrySet.size === 0) return

		registrySet.forEach((item) => {
			const code = item?.item_code
			if (!code) return
			const bucket = itemRegistry.get(code)
			if (bucket) {
				bucket.delete(item)
				if (bucket.size === 0) {
					itemRegistry.delete(code)
				}
			}
		})

		registrySet.clear()
	}

	/**
	 * Register items and initialize their stock
	 */
	function registerItems(items, registrySet) {
		if (!Array.isArray(items) || items.length === 0) return

		// Initialize stock (smart & simple!)
		stockStore.init(items)

		// Register items for tracking
		items.forEach((item) => {
			if (!item || !item.item_code) return
			let bucket = itemRegistry.get(item.item_code)
			if (!bucket) {
				bucket = new Set()
				itemRegistry.set(item.item_code, bucket)
			}
			bucket.add(item)
			registrySet.add(item)
		})
	}

	function replaceAllItems(items) {
		const next = Array.isArray(items) ? items : []
		removeRegisteredItems(registeredAllItems)
		allItems.value = next
		allItemsVersion.value += 1
		registerItems(next, registeredAllItems) // Initializes stock in stock store
		clearBaseCache()
	}

	function appendAllItems(items) {
		if (!Array.isArray(items) || items.length === 0) return
		allItems.value.push(...items)
		allItemsVersion.value += 1
		registerItems(items, registeredAllItems) // Initializes stock in stock store
		clearBaseCache()
	}

	function setSearchResults(items) {
		const next = Array.isArray(items) ? items : []
		removeRegisteredItems(registeredSearchItems)
		searchResults.value = next
		searchResultsVersion.value += 1
		registerItems(next, registeredSearchItems) // Initializes stock in stock store
		clearBaseCache()
	}

	// ========================================================================
	// FILTERED ITEMS WITH INTELLIGENT CACHING
	// ========================================================================

	/**
	 * Cache for filtered item lists to avoid redundant filtering operations.
	 * Maps filter keys (e.g., "Bundles_v1_") to filtered item arrays.
	 * Auto-managed with LRU eviction when size exceeds 10 entries.
	 *
	 * Performance Impact:
	 * - First filter: ~20-40ms (needs filtering)
	 * - Cached filter: <2ms (instant retrieval)
	 * - 20x faster for repeated filter selections
	 */
	const filteredItemsCache = new Map()
	let lastFilterKey = ''

	/**
	 * Filtered items with live stock injection - Optimized with intelligent caching
	 *
	 * This computed property provides the final item list shown in the UI.
	 * It combines three operations:
	 * 1. Filtering by item group (with intelligent caching)
	 * 2. Injecting real-time stock quantities
	 * 3. Maintaining reactivity for stock updates
	 *
	 * Performance Optimizations:
	 * - Filter result caching: Avoids re-filtering same group multiple times
	 * - Smart cache invalidation: Updates when allItems or search changes
	 * - Minimal object creation: Only creates new objects for stock injection
	 *
	 * Data Flow:
	 * 1. Source: Use searchResults if searching, otherwise allItems
	 * 2. Filter: Apply item group filter (cached if repeated)
	 * 3. Stock: Inject live stock quantities from stockStore
	 * 4. Return: Array of items with current stock levels
	 *
	 * Cache Strategy:
	 * - Cache Key: `${itemGroup}_${allItemsVersion}_${searchTerm}`
	 * - Cache Hit: Return cached filtered array (<2ms)
	 * - Cache Miss: Perform filtering, cache result (~20-40ms)
	 * - Auto-cleanup: Keep max 10 filter combinations in memory
	 *
	 * Note: Variants are shown as separate items (not deduplicated).
	 * Template items with has_variants=1 will show variant selector on click.
	 *
	 * @returns {Array<Object>} Filtered items with injected stock quantities
	 */
	/**
	 * Get all groups to filter by, including child groups for parent item groups.
	 */
	const getGroupsToFilter = (groupName) => {
		const groupInfo = itemGroups.value?.find(g => g.item_group === groupName)
		if (groupInfo?.child_groups?.length) {
			return new Set([groupName, ...groupInfo.child_groups])
		}
		return new Set([groupName])
	}

	const filteredItems = computed(() => {
		// Step 1: Determine source items (search results or all items)
		const sourceItems = searchTerm.value?.trim()
			? searchResults.value
			: allItems.value

		if (!sourceItems?.length) return []

		// Step 2: Create cache key based on current filter state
		// Key format: "itemGroup_version_searchTerm"
		// This ensures cache invalidates when data or filters change
		const filterKey = `${selectedItemGroup.value || 'all'}_${allItemsVersion.value}_${searchTerm.value || ''}`

		// Step 3: Check cache for filtered results
		let list
		if (filterKey === lastFilterKey && filteredItemsCache.has(filterKey)) {
			// Cache hit! Return cached filtered array (instant, <2ms)
			list = filteredItemsCache.get(filterKey)
		} else {
			// LARGE CATALOG OPTIMIZATION: Items are already server-filtered
			// setSelectedItemGroup() fetches items from server with group filter
			// So client-side filtering is minimal (just a sanity check)
			//
			// For 65K+ item catalogs:
			// - Server handles filtering via DB index (fast)
			// - Client receives max 100 items (already filtered)
			// - This client-side filter is just a safety net

			if (selectedItemGroup.value) {
				// User selected a specific item group tab
				// Items are ALREADY server-filtered, but verify for safety
				const groupsToFilter = getGroupsToFilter(selectedItemGroup.value)
				list = sourceItems.filter(i => groupsToFilter.has(i.item_group))
			} else if (profileItemGroups.value && profileItemGroups.value.length > 0) {
				// "All Items" tab - items fetched without group filter
				// Still filter by allowed groups as sanity check
				const allowedGroups = new Set(profileItemGroups.value.map(g => g.item_group))
				// Also include child groups in allowed set
				itemGroups.value.forEach(g => {
					if (g.child_groups) {
						g.child_groups.forEach(child => allowedGroups.add(child))
					}
				})
				list = sourceItems.filter(i => allowedGroups.has(i.item_group))
			} else {
				// No filters - show all items as-is
				list = sourceItems
			}

			// Cache the filtered results for next time
			filteredItemsCache.set(filterKey, list)
			lastFilterKey = filterKey

			// Keep cache size manageable - LRU eviction after 10 entries
			if (filteredItemsCache.size > 10) {
				const firstKey = filteredItemsCache.keys().next().value
				filteredItemsCache.delete(firstKey)
			}
		}

		// Step 4: Inject live stock quantities (optimized)
		// Use a simple map operation - O(n) complexity
		const itemsWithStock = list.map(item => {
			// Get display stock (includes reservations from cart)
			const displayStock = stockStore.getDisplayStock(item.item_code)
			// Get original server stock (without reservations)
			const originalStock = stockStore.server.get(item.item_code)?.qty || 0

			// Return item with updated stock quantities
			return {
				...item,
				actual_qty: displayStock,
				stock_qty: displayStock,
				original_stock: originalStock
			}
		})

		// Step 5: Conditional sorting - only sort when user explicitly triggers a sort filter
		// This optimizes performance by avoiding unnecessary sorting on every render
		if (sortBy.value) {
			itemsWithStock.sort((a, b) => {
				let compareResult = 0

				switch (sortBy.value) {
					case 'name':
						// Sort by item_name alphabetically
						const nameA = (a.item_name || '').toLowerCase()
						const nameB = (b.item_name || '').toLowerCase()
						compareResult = nameA.localeCompare(nameB)
						break

					case 'quantity':
						// Sort by stock quantity
						compareResult = (a.actual_qty ?? 0) - (b.actual_qty ?? 0)
						break

					case 'item_group':
						// Sort by item_group alphabetically
						const groupA = (a.item_group || '').toLowerCase()
						const groupB = (b.item_group || '').toLowerCase()
						compareResult = groupA.localeCompare(groupB)
						break

					case 'price':
						// Sort by price_list_rate (standard selling rate)
						compareResult = (a.price_list_rate ?? 0) - (b.price_list_rate ?? 0)
						break

					case 'item_code':
						// Sort by item_code alphabetically
						const codeA = (a.item_code || '').toLowerCase()
						const codeB = (b.item_code || '').toLowerCase()
						compareResult = codeA.localeCompare(codeB)
						break

					default:
						// No sorting
						compareResult = 0
				}

				// Apply sort order (asc or desc)
				return sortOrder.value === 'desc' ? -compareResult : compareResult
			})
		}

		return itemsWithStock
	})

	/**
	 * Load items with intelligent session-based caching strategy
	 *
	 * This is the primary item loading function that implements a smart caching strategy
	 * to balance performance and data freshness. It handles both filtered and unfiltered
	 * item loading scenarios with different strategies for each.
	 *
	 * CRITICAL DEPENDENCY: Must be called AFTER setPosProfile() to ensure item group
	 * filters are loaded from the POS Profile configuration.
	 *
	 * Caching Strategy (Session-Based):
	 * ┌─────────────────────┬────────────────────┬──────────────────────┐
	 * │ Scenario            │ First Load         │ Subsequent Loads     │
	 * ├─────────────────────┼────────────────────┼──────────────────────┤
	 * │ Online + Filters    │ Fetch from server  │ Use cache (instant)  │
	 * │ Online + No Filters │ Fetch first batch  │ Use cache + infinite │
	 * │ Offline + Any       │ Use cache only     │ Use cache only       │
	 * └─────────────────────┴────────────────────┴──────────────────────┘
	 *
	 * Loading Behavior by Filter Type:
	 *
	 * WITH FILTERS (POS Profile has item group filters):
	 * - Fetches ALL items from specified groups in parallel
	 * - Stores ALL items in allItems (e.g., 500 bundles + 300 electronics)
	 * - Caches ALL items for offline use
	 * - Disables infinite scroll (all data already loaded)
	 * - Client-side filtering handles tab switching (instant)
	 *
	 * WITHOUT FILTERS (Default "All Items" view):
	 * - Fetches first batch only (e.g., 20-50 items)
	 * - Enables infinite scroll for loading more
	 * - Background sync loads remaining items over time
	 * - Suitable for large catalogs (1000+ items)
	 *
	 * Performance Characteristics:
	 * - First load (online): 500-1000ms (network dependent)
	 * - Subsequent loads (cache): <50ms (instant)
	 * - Filter switching: <2ms (client-side filtering)
	 * - Offline loads: <50ms (IndexedDB retrieval)
	 *
	 * Session Freshness Tracking:
	 * Uses `serverDataFresh` flag to track if current session has fresh data.
	 * This prevents redundant server fetches on page refreshes while ensuring
	 * data is refreshed when truly needed (profile changes, forced refresh).
	 *
	 * Error Handling:
	 * - Server failure: Falls back to cache automatically
	 * - Cache failure: Shows empty state with error logged
	 * - Partial failures: Loads what's available, logs errors
	 *
	 * @param {string} profile - POS Profile name (required)
	 * @param {boolean} forceServerFetch - Force fresh server fetch, bypassing cache
	 *                                     Used after POS Profile filter updates or
	 *                                     manual refresh actions. Default: false
	 *
	 * @returns {Promise<void>} Resolves when items are loaded and stored in allItems
	 *
	 * @throws {Error} Does not throw - errors are caught and logged, fallback to cache
	 *
	 * @example
	 * // Initial load with filters
	 * await loadAllItems('Main Counter POS')
	 * // Result: Loads all items from filtered groups, stores in allItems
	 *
	 * @example
	 * // Force refresh after profile update
	 * await loadAllItems('Main Counter POS', true)
	 * // Result: Bypasses cache, fetches fresh from server
	 */
	async function loadAllItems(profile, forceServerFetch = false) {
		if (!profile) {
			return
		}

		posProfile.value = profile
		loading.value = true

		// Reset pagination state
		currentOffset.value = 0
		hasMore.value = true
		totalItemsLoaded.value = 0
		totalServerItems.value = 0

		try {
			// ====================================================================
			// STEP 1: Analyze Filter Configuration
			// ====================================================================
			// Check if POS Profile has item group filters configured
			// This determines our loading strategy:
			// - WITH filters: Load ALL items from specified groups
			// - WITHOUT filters: Load first batch, enable infinite scroll

			const itemGroupFilters = profileItemGroups.value || []
			const hasFilters = itemGroupFilters.length > 0

			log.info("Loading items with filter strategy", {
				profile,
				filterCount: itemGroupFilters.length,
				filters: hasFilters ? itemGroupFilters.map(g => g.item_group).slice(0, 3) : [],
				forceServerFetch
			})

			// ====================================================================
			// STEP 2: Check Cache, Network Status, and Item Count — IN PARALLEL
			// ====================================================================
			// Fire all checks concurrently to minimize startup latency.
			// Cache stats and item count are independent — no reason to wait for
			// one before starting the other.
			const offline = isOffline()

			const cacheStatsPromise = Promise.race([
				offlineWorker.getCacheStats(),
				new Promise((_, reject) => setTimeout(() => reject(new Error('Cache stats timeout')), 3000))
			]).catch(statsError => {
				log.warn("Cache stats unavailable, proceeding with defaults:", statsError.message)
				return { items: 0, cacheReady: false, lastSync: null }
			})

			// Start item count fetch early (only used in Strategy C, but cheap to fire now)
			// Skip when offline — count can't be fetched without network
			const countPromise = !offline ? call("pos_next.api.items.get_items_count", {
				pos_profile: profile,
			}).then(r => r?.message ?? r ?? 0).catch(countErr => {
				log.warn("Could not fetch item count:", countErr.message)
				return 0
			}) : Promise.resolve(0)

			const stats = await cacheStatsPromise
			// Preserve totalServerItems from previous sync (getCacheStats doesn't include it)
			const prevTotalServerItems = cacheStats.value?.totalServerItems
			cacheStats.value = {
				...stats,
				...(prevTotalServerItems ? { totalServerItems: prevTotalServerItems } : {}),
			}
			cacheReady.value = stats.cacheReady

			// ====================================================================
			// STEP 3: Determine Loading Strategy
			// ====================================================================
			// Session-Based Cache Decision:
			// - forceServerFetch = true: Always fetch (manual refresh)
			// - serverDataFresh = false: First load, need server data
			// - stats.cacheReady = false: Cache not available, need server data
			// - Otherwise: Use cache (already have fresh data this session)

			const shouldFetchFromServer = forceServerFetch || !serverDataFresh.value || !stats.cacheReady

			// ====================================================================
			// STRATEGY A: OFFLINE MODE - Cache Only
			// ====================================================================
			// When offline, we can only use cached data. No server fetch possible.
			// Load behavior:
			// - WITH filters: Load ALL cached items (limit: 10000)
			// - WITHOUT filters: Load first batch (limit: itemsPerPage)
			if (offline) {
				log.info("Offline mode - loading from cache")
				if (stats.cacheReady && stats.items > 0) {
					try {
						// Load first page from cache for display
						const limit = itemsPerPage.value
						const cached = await offlineWorker.searchCachedItems("", limit)

						if (cached && cached.length > 0) {
							replaceAllItems(cached)
							totalItemsLoaded.value = cached.length
							currentOffset.value = cached.length
							// Use server count if available (excludes variants), fallback to IndexedDB count
							totalServerItems.value = cacheStats.value?.totalServerItems || stats.items
							hasMore.value = cached.length >= limit
							log.success(`Loaded ${cached.length} items from cache (offline, total: ${stats.items})`)

							// Eager variant verification: Check if template items have cached variants
							const templateItems = cached.filter(item => item.has_variants)
							if (templateItems.length > 0) {
								log.info(`Verifying variants for ${templateItems.length} template items`)
								const missingVariants = []

								for (const template of templateItems) {
									const variants = await getCachedVariants(template.item_code)
									if (!variants || variants.length === 0) {
										missingVariants.push(template.item_code)
									} else {
										log.debug(`Template ${template.item_code} has ${variants.length} cached variants`)
									}
								}

								if (missingVariants.length > 0) {
									log.warn(`${missingVariants.length} template items missing variants in offline cache:`, missingVariants)
								} else {
									log.success(`All ${templateItems.length} template items have variants cached`)
								}
							}
						} else {
							replaceAllItems([])
							log.warn("No items in cache")
						}
					} catch (cacheError) {
						log.error("Cache load failed in offline mode", cacheError)
						replaceAllItems([])
					}
				} else {
					log.warn("Cache not ready in offline mode")
					replaceAllItems([])
				}
				loading.value = false
				return // Exit early - offline mode complete
			}

			// ====================================================================
			// STRATEGY B: ONLINE MODE - Cache First (if fresh)
			// ====================================================================
			// Use cache if we already have fresh data from server this session
			// This prevents redundant server fetches on page refreshes/navigations
			// Condition: serverDataFresh=true AND cache is ready
			if (!shouldFetchFromServer && stats.cacheReady && stats.items > 0) {
				log.info("Using cached items (already fetched from server this session)")
				try {
					// Load first page from cache for display
					const limit = itemsPerPage.value
					const cached = await offlineWorker.searchCachedItems("", limit)

					if (cached && cached.length > 0) {
						replaceAllItems(cached)
						totalItemsLoaded.value = cached.length
						currentOffset.value = cached.length
						// Use server count if available (excludes variants), fallback to IndexedDB count
						totalServerItems.value = cacheStats.value?.totalServerItems || stats.items
						hasMore.value = cached.length >= limit
						loading.value = false
						log.success(`Loaded ${cached.length} items from cache (total: ${stats.items})`)
						return // Exit early - cache hit, no server fetch needed
					}
				} catch (cacheError) {
					log.warn("Cache load failed, will fetch from server", cacheError)
					// Fall through to server fetch
				}
			}

			// ====================================================================
			// STRATEGY C: ONLINE MODE - Server Fetch (fresh data needed)
			// ====================================================================
			// Fetch from server when:
			// - First load (serverDataFresh = false)
			// - Forced refresh (forceServerFetch = true)
			// - Cache not available or cache load failed
			log.debug("Fetching fresh data from server")

			// ----------------------------------------------------------------
			// DYNAMIC PAGINATION: Adapt initial load to catalog size
			// ----------------------------------------------------------------
			// Small catalogs (<=1000): Load everything, skip background sync
			// Large catalogs (>1000): Load first 100, background sync the rest
			// countPromise was already fired in parallel with cache stats above
			const totalItemCount = await countPromise
			totalServerItems.value = totalItemCount
			if (totalItemCount > 0) {
				log.info(`Total catalog size: ${totalItemCount} items`)
			}

			// Determine initial load size based on catalog size
			const SMALL_CATALOG_THRESHOLD = 1000
			const isSmallCatalog = totalItemCount > 0 && totalItemCount <= SMALL_CATALOG_THRESHOLD
			const INITIAL_LIMIT = isSmallCatalog ? totalItemCount : itemsPerPage.value

			// ----------------------------------------------------------------
			// FILTERED LOADING PATH - OPTIMIZED FOR LARGE CATALOGS (65K+ items)
			// ----------------------------------------------------------------
			// Load ONLY first batch from first group. Other groups load on-demand
			// when user clicks the tab. This prevents loading 65K items at once.
			if (hasFilters && selectedItemGroup.value) {
				log.debug(`Fetching first ${INITIAL_LIMIT} items (${isSmallCatalog ? 'small catalog — loading all' : 'large catalog mode'})`)

				// Load items from first group only - other groups load on tab click
				const fetchedItems = await fetchItemsFromGroups(profile, itemGroupFilters, INITIAL_LIMIT)

				replaceAllItems(fetchedItems)
				totalItemsLoaded.value = fetchedItems.length
				currentOffset.value = fetchedItems.length

				// Small catalog: no infinite scroll needed. Large: may have more.
				hasMore.value = !isSmallCatalog && fetchedItems.length >= INITIAL_LIMIT

				if (fetchedItems.length > 0) {
					// Cache this batch for offline access (non-blocking)
					offlineWorker.cacheItems(fetchedItems).catch(err => {
						log.warn("Background item caching failed:", err.message)
					})
					cacheReady.value = true
					serverDataFresh.value = true

					log.success(`Loaded ${fetchedItems.length} items (server-side filtering)`)

					// Background caching - limit to prevent overloading IndexedDB
					cacheVariantsForTemplates(fetchedItems.slice(0, 50), profile).catch(err => {
						log.warn("Background variant caching failed:", err.message)
					})

					// Cache batch/serial data for offline use
					if (shiftStore.profileWarehouse) {
						cacheBatchSerialForItems(fetchedItems, shiftStore.profileWarehouse).catch(err => {
							log.warn("Background batch/serial caching failed:", err.message)
						})
					}

					// START BACKGROUND SYNC for offline support (large catalogs only)
					// Small catalogs already loaded everything — no sync needed
					if (!isSmallCatalog) {
						startBackgroundCacheSync(profile, itemGroupFilters)
					}
				} else {
					log.info('No items found for the selected filter groups')
				}

			// ----------------------------------------------------------------
			// UNFILTERED LOADING PATH: Lazy load with infinite scroll
			// ----------------------------------------------------------------
			// When no filters (default "All Items" view), load first batch only
			// and enable infinite scroll for progressive loading. Suitable for
			// large catalogs (1000+ items) to minimize initial load time.
			} else {
				const unfilteredLimit = isSmallCatalog ? totalItemCount : itemsPerPage.value
				log.debug(`Fetching ${unfilteredLimit} items (no filters, ${isSmallCatalog ? 'small catalog' : 'paginated'})`)

				// Fetch first batch for fast initial render
				const response = await call("pos_next.api.items.get_items", {
					pos_profile: profile,
					search_term: "",
					item_group: null, // No filter - get items from all groups
					start: 0,
					limit: unfilteredLimit,
				})
				const list = response?.message || response || []

				if (list.length > 0) {
					// Store first batch in allItems
					replaceAllItems(list)
					totalItemsLoaded.value = list.length
					currentOffset.value = list.length

					// Small catalog: no more items. Large: enable infinite scroll.
					hasMore.value = totalItemCount > unfilteredLimit

					// Cache this batch (non-blocking — background sync fills the rest)
					offlineWorker.cacheItems(list).catch(err => {
						log.warn("Background item caching failed:", err.message)
					})

					// Mark data as fresh
					serverDataFresh.value = true

					log.success(`Loaded ${list.length} items from server`)

					// Cache variants for template items (for offline use)
					// Run in background to not block UI
					cacheVariantsForTemplates(list, profile).catch(err => {
						log.warn("Background variant caching failed:", err.message)
					})

					// Cache batch/serial data for offline use
					if (shiftStore.profileWarehouse) {
						cacheBatchSerialForItems(list, shiftStore.profileWarehouse).catch(err => {
							log.warn("Background batch/serial caching failed:", err.message)
						})
					}
				}

				// Start background sync for large catalogs to cache ALL items to IndexedDB
				// Small catalogs already loaded everything
				if (!isSmallCatalog) {
					startBackgroundCacheSync(profile, [], list.length)
				}
			}
		} catch (error) {
			log.error("Error loading items", error)

			// Fallback to cache
			try {
				const cached = await offlineWorker.searchCachedItems("", itemsPerPage.value)
				replaceAllItems(cached || [])
				totalItemsLoaded.value = cached?.length || 0
				currentOffset.value = cached?.length || 0
				hasMore.value = (cached?.length || 0) >= itemsPerPage.value
				log.info(`Loaded ${cached?.length || 0} items from cache (fallback)`)
			} catch (cacheError) {
				log.error("Cache also failed", cacheError)
				replaceAllItems([])
			}
		} finally {
			loading.value = false
		}
	}

	/**
	 * Fetch items - optimized for LARGE CATALOGS (65K+ items)
	 *
	 * Strategy:
	 * - NEVER load all items (would crash with 65K items)
	 * - Always use server-side pagination
	 * - Load only what's needed for current view (max 100 items)
	 * - Server handles item_group filtering efficiently via DB index
	 */
	async function fetchItemsFromGroups(profile, itemGroups, limit = null) {
		if (!itemGroups?.length) return []

		const effectiveLimit = limit || itemsPerPage.value

		// For large catalogs: Load items from first/selected group only
		// Other groups load on-demand when user clicks the tab
		const firstGroup = itemGroups[0]?.item_group
		log.debug(`Fetching first ${effectiveLimit} items from group: ${firstGroup}`)

		try {
			const response = await call("pos_next.api.items.get_items", {
				pos_profile: profile,
				search_term: "",
				item_group: firstGroup, // Server-side filter via DB index
				start: 0,
				limit: effectiveLimit,
			})
			const items = response?.message || response || []
			log.info(`Fetched ${items.length} items from ${firstGroup}`)
			return items
		} catch (error) {
			log.error("Failed to fetch items", error)
			return []
		}
	}

	/**
	 * Fetch items for a specific item group (on-demand when user clicks tab)
	 * Optimized for large catalogs - server-side filtering
	 */
	async function fetchItemsForGroup(profile, itemGroup, start = 0, limit = null) {
		if (!itemGroup) return []

		const effectiveLimit = limit || itemsPerPage.value

		// Get expanded groups (parent + children) for filtering
		const groupInfo = itemGroups.value?.find(g => g.item_group === itemGroup)
		const groupsToFetch = groupInfo?.child_groups?.length
			? [itemGroup, ...groupInfo.child_groups]
			: [itemGroup]

		log.debug(`Fetching items for group: ${itemGroup} (includes ${groupsToFetch.length} groups)`)

		try {
			// Use bulk endpoint for multiple groups, or single endpoint for one
			if (groupsToFetch.length > 1) {
				const response = await call("pos_next.api.items.get_items_bulk", {
					pos_profile: profile,
					item_groups: JSON.stringify(groupsToFetch),
					start: start,
					limit: effectiveLimit,
				})
				return response?.message || response || []
			} else {
				const response = await call("pos_next.api.items.get_items", {
					pos_profile: profile,
					search_term: "",
					item_group: itemGroup,
					start: start,
					limit: effectiveLimit,
				})
				return response?.message || response || []
			}
		} catch (error) {
			log.error(`Failed to fetch items for group ${itemGroup}`, error)
			return []
		}
	}

	/**
	 * Fetch a specific page of items for pagination.
	 * Uses cache-first strategy: IndexedDB when cache is ready (has all items),
	 * falls back to server API when cache isn't ready, and falls back to cache
	 * on network errors.
	 *
	 * @param {number} page - 1-based page number
	 * @returns {Promise<void>}
	 */
	async function fetchPage(page) {
		if (!posProfile.value || loadingMore.value) return

		const pageSize = itemsPerPage.value
		const start = (page - 1) * pageSize

		loadingMore.value = true
		try {
			let items = []

			// Cache-first: Use IndexedDB when cache is ready or offline
			// Background sync fills IndexedDB with ALL items, so pagination
			// from cache is instant and doesn't require network round-trips
			if (isOffline() || cacheReady.value) {
				try {
					// Use group-aware cache query when a specific group is selected
					if (selectedItemGroup.value) {
						const groupsToFilter = Array.from(getGroupsToFilter(selectedItemGroup.value))
						items = await offlineWorker.searchCachedItemsByGroup(groupsToFilter, pageSize, start)
					} else {
						items = await offlineWorker.searchCachedItems("", pageSize, start)
					}
				} catch (cacheErr) {
					log.warn(`Cache fetch failed for page ${page}:`, cacheErr.message)
					items = []
				}
				if (items.length > 0) {
					replaceAllItems(items)
					currentOffset.value = start + items.length
					totalItemsLoaded.value = items.length
					log.debug(`Fetched page ${page} from cache: ${items.length} items (offset ${start})`)
					return
				}
				// Cache returned empty — if offline, nothing more we can do
				if (isOffline()) return
				// If online, fall through to server fetch
				log.debug(`Cache empty for page ${page}, falling back to server`)
			}

			// Server fetch: when cache isn't ready or cache returned empty
			if (selectedItemGroup.value) {
				items = await fetchItemsForGroup(
					posProfile.value,
					selectedItemGroup.value,
					start,
					pageSize,
				)
			} else {
				const response = await call("pos_next.api.items.get_items", {
					pos_profile: posProfile.value,
					search_term: "",
					item_group: null,
					start: start,
					limit: pageSize,
				})
				items = response?.message || response || []
			}

			if (items.length > 0) {
				replaceAllItems(items)
				currentOffset.value = start + items.length
				totalItemsLoaded.value = items.length

				// Cache for offline
				await offlineWorker.cacheItems(items)

				log.debug(`Fetched page ${page}: ${items.length} items (offset ${start})`)
			}
		} catch (error) {
			log.error(`Error fetching page ${page}`, error)
			// Network error — try cache as last resort (group-aware)
			try {
				let cached = []
				if (selectedItemGroup.value) {
					const groupsToFilter = Array.from(getGroupsToFilter(selectedItemGroup.value))
					cached = await offlineWorker.searchCachedItemsByGroup(groupsToFilter, pageSize, start)
				} else {
					cached = await offlineWorker.searchCachedItems("", pageSize, start)
				}
				if (cached && cached.length > 0) {
					replaceAllItems(cached)
					currentOffset.value = start + cached.length
					totalItemsLoaded.value = cached.length
					log.info(`Fetched page ${page} from cache (fallback): ${cached.length} items`)
				}
			} catch (cacheErr) {
				log.error(`Cache fallback also failed for page ${page}`, cacheErr)
			}
		} finally {
			loadingMore.value = false
		}
	}

	/**
	 * Load more items for infinite scroll and pagination.
	 *
	 * Fetches the next batch of items from the server using the current group
	 * context (selected item group tab or "All Items").
	 *
	 * Disabled only during active search (search results are complete).
	 *
	 * @returns {Promise<void>}
	 */
	async function loadMoreItems() {
		// ====================================================================
		// GUARD CLAUSES: Prevent loading in invalid states
		// ====================================================================

		// Guard 1: Prevent concurrent loads and check basic requirements
		if (loadingMore.value || !hasMore.value || !posProfile.value) {
			return
		}

		// Guard 2: Disable during search (search shows complete results)
		if (searchTerm.value && searchTerm.value.trim().length > 0) {
			return
		}

		// ====================================================================
		// LOAD MORE: Fetch next batch from server with current group context
		// ====================================================================

		loadingMore.value = true

		try {
			let list = []

			if (selectedItemGroup.value) {
				// User has a specific group tab selected — fetch more from that group
				list = await fetchItemsForGroup(
					posProfile.value,
					selectedItemGroup.value,
					currentOffset.value,
					itemsPerPage.value,
				)
			} else {
				// "All Items" tab — fetch next batch without group filter
				const response = await call("pos_next.api.items.get_items", {
					pos_profile: posProfile.value,
					search_term: "",
					item_group: null,
					start: currentOffset.value,
					limit: itemsPerPage.value,
				})
				list = response?.message || response || []
			}

			if (list.length > 0) {
				// Append new items to existing allItems array (maintains reactivity)
				appendAllItems(list)
				totalItemsLoaded.value += list.length

				// Update pagination state for next fetch
				currentOffset.value += list.length

				// Check if more items available
				// If we got fewer items than requested, we've reached the end
				hasMore.value = list.length >= itemsPerPage.value

				// Cache new batch for offline support
				await offlineWorker.cacheItems(list)

				log.debug(`Loaded ${list.length} more items, total: ${totalItemsLoaded.value}`)
			} else {
				// Empty response - no more items to load
				hasMore.value = false
				log.info("All items loaded from server")
			}
		} catch (error) {
			log.error("Error loading more items", error)
			// Disable infinite scroll on error to prevent retry loops
			hasMore.value = false
		} finally {
			loadingMore.value = false
		}
	}

	/**
	 * Background sync for offline support - caches ALL items to IndexedDB
	 *
	 * For large catalogs (65K+ items):
	 * - UI shows 100 items immediately (fast)
	 * - This function syncs ALL items AGGRESSIVELY for offline use
	 * - Uses CONTINUOUS batching (not interval-based) for fast sync
	 * - 65K items at 500/batch = 130 batches = ~3-5 minutes total
	 *
	 * @param {string} profile - POS Profile name
	 * @param {Array} filterGroups - Item group filters from POS Profile (optional)
	 */
	async function startBackgroundCacheSync(profile, filterGroups = [], initialOffset = 0) {
		// Cancel any previous sync and start fresh
		syncGeneration++
		const myGeneration = syncGeneration

		if (cacheSyncing.value) {
			log.info(`Cancelling previous sync, starting new sync (gen=${myGeneration})`)
		}

		const hasFilters = filterGroups.length > 0

		log.info(`Starting background sync gen=${myGeneration} ${hasFilters ? `for ${filterGroups.length} groups` : '(all items)'}`)
		cacheSyncing.value = true

		// Use larger batch size for faster sync (500 items per batch)
		const batchSize = 500
		const BATCH_DELAY_MS = 500 // Small delay between batches to not overwhelm server
		const MAX_SYNC_RETRIES = 5
		let batchCount = 0
		let consecutiveErrors = 0

		// Track unique items to avoid double-counting from overlapping groups
		const uniqueItemsSeen = new Set()

		// For unfiltered sync: start from where initial load left off
		let syncOffset = initialOffset

		// For filtered sync: track progress per group
		let groupIndex = 0
		let groupOffset = 0

		// Get all groups to sync — deduplicated (parent groups may share children)
		const groupsToSync = hasFilters
			? [...new Set(filterGroups.flatMap(g => {
				const groupInfo = itemGroups.value?.find(ig => ig.item_group === g.item_group)
				if (groupInfo?.child_groups?.length) {
					return [g.item_group, ...groupInfo.child_groups]
				}
				return [g.item_group]
			}))]
			: []

		// Fetch total item count for progress percentage (Phase 7)
		let totalServerItems = 0
		try {
			if (myGeneration !== syncGeneration) return
			const countResponse = await call("pos_next.api.items.get_items_count", {
				pos_profile: profile,
				include_variants: 1,
			})
			totalServerItems = countResponse?.message ?? countResponse ?? 0
			if (myGeneration !== syncGeneration) return
			log.info(`Total server items: ${totalServerItems}`)
		} catch (err) {
			log.warn("Could not fetch item count for progress tracking:", err.message)
		}

		// CONTINUOUS SYNC LOOP - much faster than interval-based!
		const syncLoop = async () => {
			while (myGeneration === syncGeneration) {
				try {
					let response, list

					if (hasFilters && groupsToSync.length > 0) {
						// FILTERED SYNC: Fetch items group by group
						if (groupIndex >= groupsToSync.length) {
							// All groups synced - DONE!
							break
						}

						const currentGroup = groupsToSync[groupIndex]
						log.debug(`Syncing ${currentGroup} at offset ${groupOffset}`)

						response = await call("pos_next.api.items.get_items", {
							pos_profile: profile,
							search_term: "",
							item_group: currentGroup,
							start: groupOffset,
							limit: batchSize,
							include_variants: 1,
						})
						if (myGeneration !== syncGeneration) return
						list = response?.message || response || []

						if (list.length < batchSize) {
							// Move to next group
							groupIndex++
							groupOffset = 0
							log.debug(`Completed group ${currentGroup} (${groupIndex}/${groupsToSync.length})`)
						} else {
							groupOffset += list.length
						}
					} else {
						// UNFILTERED SYNC: Fetch all items with pagination
						// Use syncOffset to skip items already loaded in initial fetch
						response = await call("pos_next.api.items.get_items", {
							pos_profile: profile,
							search_term: "",
							item_group: null,
							start: syncOffset,
							limit: batchSize,
							include_variants: 1,
						})
						if (myGeneration !== syncGeneration) return
						list = response?.message || response || []

						// Advance offset for next batch
						syncOffset += list.length

						// Check if we've reached the end
						if (list.length < batchSize) {
							// Cache this last batch and exit
							if (list.length > 0) {
								await offlineWorker.cacheItems(list)
								if (myGeneration !== syncGeneration) return
								for (const item of list) {
									if (item.item_code) uniqueItemsSeen.add(item.item_code)
								}
							}
							break
						}
					}

					if (list.length > 0) {
						// Cache the batch
						await offlineWorker.cacheItems(list)
						if (myGeneration !== syncGeneration) return

						// Track unique items for accurate progress
						for (const item of list) {
							if (item.item_code) uniqueItemsSeen.add(item.item_code)
						}
						batchCount++
						consecutiveErrors = 0 // Reset on success

						// Update stats EVERY batch for smooth progress indicator
						// Include initialOffset to account for items already loaded before sync
						const totalCached = initialOffset + uniqueItemsSeen.size
						const syncProgress = totalServerItems > 0
							? Math.round((totalCached / totalServerItems) * 100)
							: null
						cacheStats.value = {
							...cacheStats.value,
							items: totalCached,
							totalServerItems,
							syncProgress,
							lastSync: new Date().toISOString()
						}
						cacheReady.value = true

						// Log progress every 10 batches (5000 items)
						if (batchCount % 10 === 0) {
							const progressStr = syncProgress != null ? ` (${syncProgress}%)` : ''
							log.info(`Sync progress: ${totalCached} items cached${progressStr} (${batchCount} batches)`)
						}

						// Note: Variants are included in the sync via include_variants=1,
						// so no need for separate cacheVariantsForTemplates call here

						// Small delay to not overwhelm server/browser
						await new Promise(resolve => setTimeout(resolve, BATCH_DELAY_MS))
					}
				} catch (error) {
					consecutiveErrors++
					if (consecutiveErrors >= MAX_SYNC_RETRIES) {
						log.error(`Sync failed after ${MAX_SYNC_RETRIES} consecutive errors, stopping`, error.message)
						break
					}
					const backoffMs = Math.min(2000 * Math.pow(2, consecutiveErrors - 1), 30000)
					log.warn(`Sync batch error (${consecutiveErrors}/${MAX_SYNC_RETRIES}), retrying in ${backoffMs}ms...`, error.message)
					await new Promise(resolve => setTimeout(resolve, backoffMs))
				}
			}

			// Only finalize if this sync generation is still active
			if (myGeneration !== syncGeneration) {
				log.info(`Sync gen=${myGeneration} cancelled (current gen=${syncGeneration})`)
				return
			}

			// Sync complete!
			const finalStats = await offlineWorker.getCacheStats()
			const finalCached = initialOffset + uniqueItemsSeen.size
			cacheStats.value = {
				...finalStats,
				totalServerItems,
				syncProgress: totalServerItems > 0 ? Math.round((finalCached / totalServerItems) * 100) : null,
			}
			cacheReady.value = true
			cacheSyncing.value = false
			log.success(`Background sync COMPLETE - ${finalCached} items cached in ${batchCount} batches`)

			// Cache batch/serial data after items are synced (in background)
			if (shiftStore.profileWarehouse && finalCached > 0) {
				log.info("Starting batch/serial data sync...")
				// This runs in background, don't await
				offlineWorker.searchCachedItems("", 10000).then(async (items) => {
					const batchSerialItems = items.filter(i => i.has_batch_no || i.has_serial_no)
					if (batchSerialItems.length > 0) {
						await cacheBatchSerialForItems(batchSerialItems, shiftStore.profileWarehouse)
					}
				}).catch(err => log.warn("Batch/serial sync failed:", err.message))
			}
		}

		// Start the sync loop (runs in background via microtask queue)
		syncLoop()
	}

	function stopBackgroundCacheSync() {
		syncGeneration++ // Cancel any in-flight sync loop
		if (cacheSyncing.value) {
			cacheSyncing.value = false
			log.info("Background cache sync stopped")
		}
	}

	async function searchItems(term) {
		// Clear previous debounce timer
		if (searchDebounceTimer) {
			clearTimeout(searchDebounceTimer)
		}

		// If search term is empty, clear search results
		if (!term || term.trim().length === 0) {
			setSearchResults([])
			searching.value = false
			return
		}

		// Debounce search - wait 300ms after user stops typing
		return new Promise((resolve) => {
			searchDebounceTimer = setTimeout(async () => {
				searching.value = true

				// Get search limit once for this search operation
				const searchLimit = performanceConfig.get("searchBatchSize") || 500

				try {
					// CACHE-FIRST STRATEGY:
					// 1. Search IndexedDB cache first (instant!)
					// 2. If cache has results, show them immediately
					// 3. Then search server for fresh results in background

					log.debug(`Searching cache for: "${term}"`)
					const cached = await offlineWorker.searchCachedItems(term, searchLimit)

					if (cached && cached.length > 0) {
						// Show cached results immediately (instant!)
						setSearchResults(cached)
						searching.value = false
						log.success(`Found ${cached.length} items in cache`)

						// Resolve with cached results
						resolve(cached)
					}

					// Now search server in background for fresh results
					log.debug(`Searching server for: "${term}"`)
					const response = await call("pos_next.api.items.get_items", {
						pos_profile: posProfile.value,
						search_term: term,
						item_group: selectedItemGroup.value,
						start: 0,
						limit: searchLimit, // Dynamically adjusted based on device performance
					})
					const serverResults = response?.message || response || []

					if (serverResults.length > 0) {
						// Update with fresh server results
						setSearchResults(serverResults)
						log.success(`Found ${serverResults.length} items on server`)

						// Cache server results for future searches
						await offlineWorker.cacheItems(serverResults)

						// If we didn't resolve with cache, resolve with server results
						if (!cached || cached.length === 0) {
							resolve(serverResults)
						}
					} else if (!cached || cached.length === 0) {
						// No results from either cache or server
						setSearchResults([])
						resolve([])
					}
				} catch (error) {
					log.error("Error searching items", error)

					// If we haven't shown cache results yet, try cache as fallback
					if (!searchResults.value || searchResults.value.length === 0) {
						try {
							const cached = await offlineWorker.searchCachedItems(term, searchLimit)
							setSearchResults(cached || [])
							resolve(cached || [])
							log.info(`Fallback: found ${cached?.length || 0} items in cache`)
						} catch (cacheError) {
							log.error("Cache search also failed", cacheError)
							setSearchResults([])
							resolve([])
						}
					}
				} finally {
					searching.value = false
				}
			}, performanceConfig.get("searchDebounce")) // Reactive: auto-adjusted 500ms/300ms/150ms based on device
		})
	}

	async function loadItemGroups() {
		if (posProfile.value) {
			await itemGroupsResource.reload()
		}
	}

	async function searchByBarcode(barcode) {
		try {
			if (!posProfile.value) {
				log.error("No POS Profile set in store")
				throw new Error("POS Profile not set")
			}

			log.debug("Calling searchByBarcode API", { posProfile: posProfile.value })

			const result = await searchByBarcodeResource.submit({
				barcode: barcode,
				pos_profile: posProfile.value,
			})

			const item = result?.message || result
			return item
		} catch (error) {
			log.error("Store searchByBarcode error", error)
			throw error
		}
	}

	async function getItem(itemCode) {
		try {
			const cacheReady = await offlineWorker.isCacheReady()
			if (isOffline() || cacheReady) {
				const items = await offlineWorker.searchCachedItems(itemCode, 1)
				return items?.[0] || null
			} else {
				// Fallback to server (implement if needed)
				return null
			}
		} catch (error) {
			log.error("Error getting item", error)
			return null
		}
	}

	function setSearchTerm(term) {
		searchTerm.value = term

		// Trigger server-side search when term is entered
		if (term && term.trim().length > 0) {
			searchItems(term)
		} else {
			// Clear search results when term is cleared
			setSearchResults([])
			searching.value = false
		}
	}

	function clearSearch() {
		searchTerm.value = ""
		setSearchResults([])
		searching.value = false

		// Clear debounce timer
		if (searchDebounceTimer) {
			clearTimeout(searchDebounceTimer)
			searchDebounceTimer = null
		}
	}

	/**
	 * Set sorting filter - triggers sorting only when explicitly called
	 * @param {string} field - Field to sort by: 'name', 'quantity', 'item_group', 'price', 'item_code'
	 * @param {string} order - Sort order: 'asc' or 'desc' (default: 'asc')
	 */
	function setSortFilter(field, order = 'asc') {
		sortBy.value = field
		sortOrder.value = order

		// Clear filtered items cache to force re-computation with new sort
		clearBaseCache()

		log.debug(`Sort filter set: ${field} ${order}`)
	}

	/**
	 * Clear sorting filter - returns to unsorted view
	 */
	function clearSortFilter() {
		sortBy.value = null
		sortOrder.value = 'asc'

		// Clear filtered items cache to force re-computation
		clearBaseCache()

		log.debug('Sort filter cleared')
	}

	function cleanup() {
		// Stop background sync when store is destroyed
		stopBackgroundCacheSync()

		// Clear timers
		if (searchDebounceTimer) {
			clearTimeout(searchDebounceTimer)
			searchDebounceTimer = null
		}

		// Clean up real-time POS Profile update handler
		if (posProfileUpdateCleanup) {
			posProfileUpdateCleanup()
			posProfileUpdateCleanup = null
		}
	}

	async function setSelectedItemGroup(group) {
		selectedItemGroup.value = group
		clearBaseCache()

		// LARGE CATALOG OPTIMIZATION: Fetch items from server when group changes
		// Client-side filtering doesn't work for 65K+ items
		if (posProfile.value) {
			loading.value = true
			try {
				const pageSize = itemsPerPage.value
				const offline = isOffline()

				// ================================================================
				// OFFLINE PATH: Load from IndexedDB cache using item_group index
				// ================================================================
				if (offline) {
					try {
						let items = []
						let totalCount = 0
						if (group) {
							// Get expanded groups (parent + children)
							const groupsToFilter = Array.from(getGroupsToFilter(group))
							const [cached, count] = await Promise.all([
								offlineWorker.searchCachedItemsByGroup(groupsToFilter, pageSize, 0),
								offlineWorker.countCachedItemsByGroup(groupsToFilter),
							])
							items = cached || []
							totalCount = count || items.length
						} else {
							// "All Items" tab — load first page alphabetically
							const [cached, stats] = await Promise.all([
								offlineWorker.searchCachedItems("", pageSize, 0),
								offlineWorker.getCacheStats(),
							])
							items = cached || []
							totalCount = stats?.totalServerItems || stats?.items || items.length
						}

						if (items.length > 0) {
							replaceAllItems(items)
							totalItemsLoaded.value = items.length
							currentOffset.value = items.length
							totalServerItems.value = totalCount
							hasMore.value = items.length >= pageSize
							log.info(`Loaded ${items.length} cached items for group: ${group || 'All Items'} (offline, total: ${totalCount})`)
						} else {
							replaceAllItems([])
							log.warn(`No cached items for group: ${group || 'All Items'} (offline)`)
						}
					} catch (cacheErr) {
						log.error("Cache load failed for group tab (offline):", cacheErr.message)
						replaceAllItems([])
					}
					loading.value = false
					// Re-run search with new group context if active
					if (searchTerm.value?.trim()) {
						if (searchDebounceTimer) {
							clearTimeout(searchDebounceTimer)
							searchDebounceTimer = null
						}
						searchItems(searchTerm.value)
					}
					return
				}

				// ================================================================
				// ONLINE PATH: Fetch from server
				// ================================================================
				// Fetch first page + total count in parallel for instant pagination
				const countPromise = call("pos_next.api.items.get_items_count", {
					pos_profile: posProfile.value,
					item_group: group || undefined,
				}).catch(err => {
					log.warn("Could not fetch item count:", err.message)
					return 0
				})

				let items = []
				if (group) {
					// Specific group: fetch first page for that group + children
					items = await fetchItemsForGroup(posProfile.value, group, 0, pageSize)
					log.info(`Loaded ${items.length} items for group: ${group}`)
				} else {
					// "All Items" tab: fetch first page (no group filter)
					const response = await call("pos_next.api.items.get_items", {
						pos_profile: posProfile.value,
						search_term: "",
						item_group: null,
						start: 0,
						limit: pageSize,
					})
					items = response?.message || response || []
					log.info(`Loaded ${items.length} items for "All Items" tab`)
				}

				// Get total count for pagination
				const countResult = await countPromise
				totalServerItems.value = countResult?.message ?? countResult ?? items.length

				if (items.length > 0) {
					replaceAllItems(items)
					totalItemsLoaded.value = items.length
					currentOffset.value = items.length
					hasMore.value = items.length >= pageSize
				} else if (group && cacheSyncing.value) {
					// Server returned 0 but sync is still caching items — try cache fallback
					try {
						const groupsToFilter = Array.from(getGroupsToFilter(group))
						const cached = await offlineWorker.searchCachedItemsByGroup(groupsToFilter, 500, 0)
						if (cached && cached.length > 0) {
							replaceAllItems(cached)
							totalItemsLoaded.value = cached.length
							currentOffset.value = cached.length
							hasMore.value = false
							log.info(`Loaded ${cached.length} cached items for group: ${group} (sync in progress)`)
						}
					} catch (cacheErr) {
						log.warn("Cache fallback for group tab failed:", cacheErr.message)
					}
				}
			} catch (error) {
				log.error(`Failed to load items for group ${group || 'All Items'}`, error)

				// Network error — try cache as fallback
				try {
					const pageSize = itemsPerPage.value
					let items = []
					let totalCount = 0
					if (group) {
						const groupsToFilter = Array.from(getGroupsToFilter(group))
						const [cached, count] = await Promise.all([
							offlineWorker.searchCachedItemsByGroup(groupsToFilter, pageSize, 0),
							offlineWorker.countCachedItemsByGroup(groupsToFilter),
						])
						items = cached || []
						totalCount = count || items.length
					} else {
						items = await offlineWorker.searchCachedItems("", pageSize, 0) || []
						totalCount = items.length
					}
					if (items.length > 0) {
						replaceAllItems(items)
						totalItemsLoaded.value = items.length
						currentOffset.value = items.length
						totalServerItems.value = totalCount
						hasMore.value = items.length >= pageSize
						log.info(`Loaded ${items.length} cached items for group: ${group || 'All Items'} (network error fallback)`)
					}
				} catch (cacheErr) {
					log.warn("Cache fallback after network error failed:", cacheErr.message)
				}
			} finally {
				loading.value = false
			}
		}

		// If there's an active search, re-run it with the new group context
		if (searchTerm.value?.trim()) {
			if (searchDebounceTimer) {
				clearTimeout(searchDebounceTimer)
				searchDebounceTimer = null
			}
			searchItems(searchTerm.value)
		}
	}

	/**
	 * Update cart items - delegates to stock store
	 */
	function setCartItems(items) {
		cartItems.value = items
		stockStore.reserve(items) // Simple!
	}

	/**
	 * Set POS Profile and load item group filters
	 * OPTIMIZED: Single API call returns both profile data AND hierarchical item groups
	 * @param {string} profile - POS Profile name
	 * @param {boolean} autoLoadItems - Automatically load items after setting profile (default: true)
	 */
	async function setPosProfile(profile, autoLoadItems = true) {
		posProfile.value = profile
		serverDataFresh.value = false

		if (posProfileUpdateCleanup) {
			posProfileUpdateCleanup()
			posProfileUpdateCleanup = null
		}

		if (!profile) {
			profileItemGroups.value = []
			itemGroups.value = []
			return
		}

		try {
			// Single API call returns EVERYTHING - no need for separate loadItemGroups()
			const data = await call("pos_next.api.pos_profile.get_pos_profile_data", {
				pos_profile: profile
			})

			// Set profile item groups (raw from child table)
			profileItemGroups.value = data?.pos_profile?.item_groups || []

			// Set hierarchical item groups (with child_groups) - INSTANT tab display!
			itemGroups.value = data?.item_groups_hierarchy || []
			log.info(`Loaded ${itemGroups.value.length} item groups with hierarchy`)

			// Cache profile data for offline use (survives component remount)
			try {
				sessionStorage.setItem(`pos_profile_data:${profile}`, JSON.stringify({
					profileItemGroups: profileItemGroups.value,
					itemGroups: itemGroups.value,
				}))
			} catch (e) {
				// sessionStorage might be full or unavailable
			}

			// Set up real-time listener
			posProfileUpdateCleanup = onPosProfileUpdate(async (updateData) => {
				await handlePosProfileUpdateWithRecovery(updateData, profile)
			})

			// Stop any existing sync before loading items for new profile
			stopBackgroundCacheSync()

			// Load items in background (non-blocking)
			if (autoLoadItems) {
				loadAllItems(profile)
			}
		} catch (error) {
			log.error("Error fetching POS Profile data", error)

			// Offline fallback: restore item groups from session cache
			// This keeps group tabs visible after language change while offline
			try {
				const cached = sessionStorage.getItem(`pos_profile_data:${profile}`)
				if (cached) {
					const parsed = JSON.parse(cached)
					profileItemGroups.value = parsed.profileItemGroups || []
					itemGroups.value = parsed.itemGroups || []
					log.info(`Restored ${itemGroups.value.length} item groups from session cache (offline)`)

					// Still load items from IndexedDB cache
					if (autoLoadItems) {
						loadAllItems(profile)
					}
					return
				}
			} catch (e) {
				// Cache parse failed
			}

			profileItemGroups.value = []
			itemGroups.value = []
		}
	}

	function invalidateCache() {
		// Clear caches to force UI refresh with updated stock
		clearBaseCache()
	}

	// Stock delegates - Smart & minimal!
	const applyStockUpdates = (updates) => stockStore.update(updates)
	const refreshStockFromServer = (codes, wh) => stockStore.refresh(codes, wh)

	return {
		// ========================================================================
		// CORE STATE
		// ========================================================================
		allItems,
		searchResults,
		searchTerm,
		selectedItemGroup,
		itemGroups,
		profileItemGroups,
		loading,
		loadingMore,
		searching,
		posProfile,
		cartItems,
		hasMore,
		totalItemsLoaded,
		totalServerItems,
		currentOffset,
		cacheReady,
		cacheSyncing,
		cacheStats,
		sortBy,
		sortOrder,

		// ========================================================================
		// COMPUTED PROPERTIES
		// ========================================================================
		filteredItems, // Injects live stock from stock store

		// ========================================================================
		// ACTIONS - Items & Search
		// ========================================================================
		loadAllItems,
		loadMoreItems,
		fetchPage,
		searchItems,
		loadItemGroups,
		searchByBarcode,
		getItem,
		setSearchTerm,
		clearSearch,
		setSelectedItemGroup,
		setCartItems, // Delegates to stock store for reservations
		setPosProfile,
		startBackgroundCacheSync,
		stopBackgroundCacheSync,
		cleanup,
		invalidateCache,
		setSortFilter,
		clearSortFilter,

		// ========================================================================
		// STOCK ACTIONS - Delegates to stock store
		// ========================================================================
		applyStockUpdates,        // Delegates to stockStore.applyUpdates
		refreshStockFromServer,   // Delegates to stockStore.refreshFromServer

		// ========================================================================
		// STOCK STORE ACCESS
		// ========================================================================
		stockStore, // Direct access to dedicated stock store

		// ========================================================================
		// RESOURCES
		// ========================================================================
		itemGroupsResource,
		searchByBarcodeResource,
	}
})
