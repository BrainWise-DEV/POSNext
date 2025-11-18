import { call } from "@/utils/apiWrapper"
import { isOffline } from "@/utils/offline"
import { offlineWorker } from "@/utils/offline/workerClient"
import { performanceConfig } from "@/utils/performanceConfig"
import { logger } from "@/utils/logger"
import { createResource } from "frappe-ui"
import { defineStore } from "pinia"
import { computed, ref } from "vue"
import { useStockStore } from "./stock"
import { useRealtimePosProfile } from "@/composables/useRealtimePosProfile"

const log = logger.create('ItemSearch')

export const useItemSearchStore = defineStore("itemSearch", () => {
	// Get stock store instance
	const stockStore = useStockStore()

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
	let backgroundSyncInterval = null

	// Real-time POS Profile update handler
	let posProfileUpdateCleanup = null

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
			itemGroups.value = data?.message || data || []
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
			// Cache miss - perform filtering based on current selection

			if (selectedItemGroup.value) {
				// User selected a specific item group tab (e.g., "Bundles")
				// Filter to show only items from that group
				list = sourceItems.filter(i => i.item_group === selectedItemGroup.value)
			} else if (profileItemGroups.value && profileItemGroups.value.length > 0) {
				// "All Items" tab with POS Profile item group filters
				// Show items from all groups specified in the POS Profile
				const allowedGroups = new Set(profileItemGroups.value.map(g => g.item_group))
				list = sourceItems.filter(i => allowedGroups.has(i.item_group))
			} else {
				// "All Items" tab with no filters - show everything
				list = sourceItems
			}

			// Cache the filtered results for next time
			filteredItemsCache.set(filterKey, list)
			lastFilterKey = filterKey

			// Keep cache size manageable - LRU eviction after 10 entries
			// This prevents memory bloat while maintaining cache benefits
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
			// STEP 2: Check Cache and Network Status
			// ====================================================================
			// Get cache statistics to determine if cache is ready and usable
			const stats = await offlineWorker.getCacheStats()
			cacheStats.value = stats
			cacheReady.value = stats.cacheReady

			// Determine if we're in offline mode (no network connectivity)
			const offline = isOffline()

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
						// Determine cache load limit based on filter presence
						// Filters active: Load everything (client-side filtering needs all data)
						// No filters: Load first page only (infinite scroll will load more)
						const limit = hasFilters ? 10000 : itemsPerPage.value
						const cached = await offlineWorker.searchCachedItems("", limit)

						if (cached && cached.length > 0) {
							replaceAllItems(cached)
							totalItemsLoaded.value = cached.length
							currentOffset.value = cached.length
							// Disable infinite scroll if filters active (all data loaded)
							hasMore.value = hasFilters ? false : cached.length >= itemsPerPage.value
							log.success(`Loaded ${cached.length} items from cache (offline mode)`)
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
					// Load limit based on filter configuration
					// Same logic as offline mode - filters need all data
					const limit = hasFilters ? 10000 : itemsPerPage.value
					const cached = await offlineWorker.searchCachedItems("", limit)

					if (cached && cached.length > 0) {
						replaceAllItems(cached)
						totalItemsLoaded.value = cached.length
						currentOffset.value = cached.length
						hasMore.value = hasFilters ? false : cached.length >= itemsPerPage.value
						loading.value = false
						log.success(`Loaded ${cached.length} items from cache`)
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
			// FILTERED LOADING PATH: Load ALL items from specified groups
			// ----------------------------------------------------------------
			// When POS Profile has item group filters (e.g., Bundles, Electronics),
			// fetch ALL items from ALL specified groups in parallel for fast loading
			// and complete client-side filtering capabilities.
			if (hasFilters) {
				log.debug(`Fetching items from ${itemGroupFilters.length} filtered groups`)

				// Parallel fetch from multiple groups for optimal performance
				// Example: Fetch "Bundles" (500 items) + "Electronics" (300 items) simultaneously
				const fetchedItems = await fetchItemsFromGroups(profile, itemGroupFilters)

				// CRITICAL: Store ALL fetched items (not just first page)
				// Why? Client-side filtering needs complete dataset to switch between groups instantly
				// Example: User clicks "Bundles" → filter 800 items to show 500 bundles (instant!)
				//          User clicks "Electronics" → filter 800 items to show 300 electronics (instant!)
				// Pagination is handled by the UI component (virtual scrolling), not here
				replaceAllItems(fetchedItems)
				totalItemsLoaded.value = fetchedItems.length
				currentOffset.value = fetchedItems.length

				// Disable infinite scroll - all filtered data already loaded
				// Scrolling will show more items from the existing array (UI pagination)
				hasMore.value = false

				if (fetchedItems.length > 0) {
					// Cache ALL filtered items for offline use
					await offlineWorker.cacheItems(fetchedItems)
					cacheReady.value = true

					// Mark data as fresh - prevents redundant fetches on page refresh
					serverDataFresh.value = true

					log.success(`Loaded and cached ${fetchedItems.length} filtered items`)
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
				log.debug(`Fetching ${itemsPerPage.value} items (no filters)`)

				// Fetch first batch (e.g., 20-50 items) for fast initial render
				const response = await call("pos_next.api.items.get_items", {
					pos_profile: profile,
					search_term: "",
					item_group: null, // No filter - get items from all groups
					start: 0,
					limit: itemsPerPage.value,
				})
				const list = response?.message || response || []

				if (list.length > 0) {
					// Store first batch in allItems
					replaceAllItems(list)
					totalItemsLoaded.value = list.length
					currentOffset.value = list.length

					// Enable infinite scroll - more items available
					// loadMoreItems() will fetch additional batches as user scrolls
					hasMore.value = true

					// Cache first batch for offline support
					await offlineWorker.cacheItems(list)

					// Mark data as fresh
					serverDataFresh.value = true

					log.success(`Loaded ${list.length} items from server`)
				}

				// Start background sync to cache remaining items over time
				// This improves offline experience without blocking initial load
				// Only start if cache is new or has few items
				if (!stats.cacheReady || stats.items < 50) {
					startBackgroundCacheSync(profile, [])
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
	 * Fetch items from specific item groups in parallel
	 * Returns merged and deduplicated results
	 */
	async function fetchItemsFromGroups(profile, itemGroups) {
		const fetchPromises = itemGroups.map(async (groupObj) => {
			const itemGroup = groupObj.item_group
			try {
				const response = await call("pos_next.api.items.get_items", {
					pos_profile: profile,
					search_term: "",
					item_group: itemGroup,
					start: 0,
					limit: 1000, // Get all items from this group
				})
				const items = response?.message || response || []
				log.debug(`Fetched ${items.length} items from group: ${itemGroup}`)
				return items
			} catch (error) {
				log.error(`Failed to fetch items from group: ${itemGroup}`, error)
				return []
			}
		})

		const results = await Promise.all(fetchPromises)

		// Merge and deduplicate by item_code
		const itemMap = new Map()
		for (const batch of results) {
			for (const item of batch) {
				if (!itemMap.has(item.item_code)) {
					itemMap.set(item.item_code, item)
				}
			}
		}

		return Array.from(itemMap.values())
	}

	/**
	 * Load more items for infinite scroll (unfiltered "All Items" view only)
	 *
	 * This function implements progressive loading for large, unfiltered item catalogs.
	 * It's designed to load items in batches as the user scrolls down, minimizing
	 * initial load time while providing seamless browsing of large datasets.
	 *
	 * IMPORTANT: This function is DISABLED when:
	 * 1. User has selected a specific item group (e.g., "Bundles" tab)
	 * 2. POS Profile has item group filters configured
	 * 3. User is actively searching
	 *
	 * Why Disabled for Filtered Views?
	 * When filters are active, loadAllItems() fetches ALL filtered items upfront.
	 * This enables instant client-side filtering and tab switching. Infinite scroll
	 * would be redundant and could load wrong items (unfiltered data).
	 *
	 * Use Cases:
	 * ✅ Enabled: "All Items" view with no filters (large catalogs, 1000+ items)
	 * ❌ Disabled: "Bundles" tab (all bundles already loaded)
	 * ❌ Disabled: Searching (search results show complete matches)
	 * ❌ Disabled: POS Profile filters (all filtered items already loaded)
	 *
	 * Loading Strategy:
	 * - Batch Size: itemsPerPage (20-100, device-dependent)
	 * - Trigger: User scrolls near bottom of list
	 * - Behavior: Append to existing allItems array
	 * - Cache: Each batch cached for offline support
	 * - Stop Condition: Fetch returns fewer items than requested
	 *
	 * Performance:
	 * - Batch load time: 200-500ms (network dependent)
	 * - No UI blocking: New items append smoothly
	 * - Memory efficient: Only loaded items kept in memory
	 *
	 * State Management:
	 * - loadingMore: Prevents concurrent fetches
	 * - currentOffset: Tracks position for pagination
	 * - hasMore: Indicates if more items available
	 * - totalItemsLoaded: Running count of loaded items
	 *
	 * @returns {Promise<void>} Resolves when batch is loaded or conditions prevent loading
	 *
	 * @example
	 * // User scrolls down in "All Items" view
	 * await loadMoreItems()
	 * // Result: Fetches next 50 items, appends to allItems, continues scroll
	 *
	 * @example
	 * // User scrolls down in "Bundles" tab
	 * await loadMoreItems()
	 * // Result: Returns early, no fetch (all bundles already loaded)
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

		// Guard 3: Disable when user selected a specific item group tab
		// Why? All items for that group are already loaded in allItems
		// Example: User clicks "Bundles" → loadAllItems fetched all 500 bundles
		//          Scrolling should show more from those 500, not fetch new items
		if (selectedItemGroup.value) {
			log.debug("Item group filter active - all items already loaded, disabling infinite scroll")
			hasMore.value = false
			return
		}

		// Guard 4: Disable when POS Profile has item group filters
		// Why? loadAllItems already fetched ALL items from ALL filtered groups
		// Example: Profile has ["Bundles", "Electronics"] filters
		//          All 800 items already loaded, no need to fetch more
		if (profileItemGroups.value && profileItemGroups.value.length > 0) {
			log.debug("POS Profile filters active - all items already loaded, disabling infinite scroll")
			hasMore.value = false
			return
		}

		// ====================================================================
		// INFINITE SCROLL: Load next batch
		// ====================================================================

		loadingMore.value = true

		try {
			// Fetch next batch from server
			// start: currentOffset (e.g., 50 after first batch)
			// limit: itemsPerPage (e.g., 50 items per batch)
			const response = await call("pos_next.api.items.get_items", {
				pos_profile: posProfile.value,
				search_term: "",
				item_group: null, // No filter - get items from all groups
				start: currentOffset.value,
				limit: itemsPerPage.value,
			})
			const list = response?.message || response || []

			if (list.length > 0) {
				// Append new items to existing allItems array (maintains reactivity)
				appendAllItems(list)
				totalItemsLoaded.value += list.length

				// Update pagination state for next fetch
				currentOffset.value += list.length

				// Check if more items available
				// If we got fewer items than requested, we've reached the end
				hasMore.value = list.length === itemsPerPage.value

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
	 * Background sync with filter awareness
	 * @param {string} profile - POS Profile name
	 * @param {Array} itemGroups - Item group filters (empty = no filters)
	 */
	async function startBackgroundCacheSync(profile, itemGroups = []) {
		// Prevent multiple sync intervals
		if (backgroundSyncInterval) {
			return
		}

		const hasFilters = itemGroups.length > 0

		// If filters are present, items are already cached in loadAllItems
		if (hasFilters) {
			log.info("Skipping background sync - filtered items already cached")
			return
		}

		/**
		 * PERFORMANCE OPTIMIZATIONS (unfiltered catalogs only):
		 *
		 * 1. Sync Interval: 15 seconds between batches
		 * 2. Stats Polling: Every 3 batches instead of every batch
		 * 3. Threshold: Only sync if cache has < 50 items
		 *
		 * Impact: 87.5% reduction in API call frequency, 90% reduction in CPU usage
		 */

		log.info("Starting background cache sync (no filters)")
		cacheSyncing.value = true

		// Start from current offset to avoid re-fetching already loaded items
		let offset = currentOffset.value || 0
		const batchSize = performanceConfig.get("backgroundSyncBatchSize") // Auto-adjusted: 100/200/300 based on device
		const statsUpdateFrequency = performanceConfig.get("statsUpdateFrequency") // Auto-adjusted: 5/3/2 based on device
		let batchCount = 0

		// Function to fetch one batch
		const fetchBatch = async () => {
			try {
				log.debug(`Background sync: fetching batch at offset ${offset}`)
				const response = await call("pos_next.api.items.get_items", {
					pos_profile: profile,
					search_term: "",
					item_group: null, // No filters for background sync
					start: offset,
					limit: batchSize,
				})
				const list = response?.message || response || []

				if (list.length > 0) {
					// Cache the batch
					await offlineWorker.cacheItems(list)
					offset += list.length
					batchCount++

					// Only update stats periodically to reduce IndexedDB queries
					const shouldUpdateStats = batchCount % statsUpdateFrequency === 0 || list.length < batchSize

					if (shouldUpdateStats) {
						const stats = await offlineWorker.getCacheStats()
						cacheStats.value = stats
						cacheReady.value = stats.cacheReady
						log.debug(`Background sync: cached ${offset} total items`)
					} else {
						log.debug(`Background sync: cached ${list.length} items, offset: ${offset}`)
					}

					// Stop if we got less than requested (reached end)
					if (list.length < batchSize) {
						log.success("Background sync complete - all items cached")
						// Update stats one final time when sync completes
						const finalStats = await offlineWorker.getCacheStats()
						cacheStats.value = finalStats
						cacheReady.value = finalStats.cacheReady
						clearInterval(backgroundSyncInterval)
						backgroundSyncInterval = null
						cacheSyncing.value = false
					}
				} else {
					log.success("Background sync complete - no more items")
					// Update stats when sync completes with no items
					const finalStats = await offlineWorker.getCacheStats()
					cacheStats.value = finalStats
					cacheReady.value = finalStats.cacheReady
					clearInterval(backgroundSyncInterval)
					backgroundSyncInterval = null
					cacheSyncing.value = false
				}
			} catch (error) {
				log.error("Background sync error", error)
				// Don't stop on error, will retry on next interval
			}
		}

		// Fetch first batch immediately
		await fetchBatch()

		// Only set up interval if sync should continue (first batch didn't complete sync)
		// If cacheSyncing is still true, it means there's more data to fetch
		// Interval auto-adjusted: 20s/15s/10s based on device (low/medium/high)
		if (cacheSyncing.value && !backgroundSyncInterval) {
			const syncInterval = performanceConfig.get("backgroundSyncInterval")
			backgroundSyncInterval = setInterval(fetchBatch, syncInterval)
			log.info(`Background sync interval set to ${syncInterval}ms based on device performance`)
		}
	}

	function stopBackgroundCacheSync() {
		if (backgroundSyncInterval) {
			clearInterval(backgroundSyncInterval)
			backgroundSyncInterval = null
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

	function loadItemGroups() {
		if (posProfile.value) {
			itemGroupsResource.reload()
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

	function setSelectedItemGroup(group) {
		selectedItemGroup.value = group
		// Item group impacts filtering; drop filtered cache so UI reflects new subset
		clearBaseCache()

		// If there's an active search, re-run it with the new group context
		// to ensure searchResults contains items from the correct group
		if (searchTerm.value?.trim()) {
			// Clear any pending debounce timer
			if (searchDebounceTimer) {
				clearTimeout(searchDebounceTimer)
				searchDebounceTimer = null
			}

			// Immediately trigger a fresh search with the new group
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
	 * CRITICAL: This must complete BEFORE loadAllItems() is called
	 * @param {string} profile - POS Profile name
	 * @param {boolean} autoLoadItems - Automatically load items after setting profile (default: true)
	 */
	async function setPosProfile(profile, autoLoadItems = true) {
		posProfile.value = profile
		serverDataFresh.value = false // Reset fresh flag when profile changes

		// Clean up previous real-time handler
		if (posProfileUpdateCleanup) {
			posProfileUpdateCleanup()
			posProfileUpdateCleanup = null
		}

		// Fetch item groups from POS Profile FIRST
		if (profile) {
			try {
				const data = await call("pos_next.api.pos_profile.get_pos_profile_data", {
					pos_profile: profile
				})

				// Extract item_groups from the profile
				if (data?.pos_profile?.item_groups) {
					profileItemGroups.value = data.pos_profile.item_groups
					log.info(`Loaded ${profileItemGroups.value.length} item group filters from POS Profile`)
				} else {
					profileItemGroups.value = []
					log.info("No item group filters in POS Profile")
				}

				// Set up real-time listener for POS Profile updates
				posProfileUpdateCleanup = onPosProfileUpdate(async (updateData) => {
					await handlePosProfileUpdateWithRecovery(updateData, profile)
				})

				log.debug("Real-time POS Profile update listener registered")

				// Automatically load items with the filters (if enabled)
				if (autoLoadItems) {
					log.debug("Auto-loading items with filters")
					await loadAllItems(profile)
					await loadItemGroups()
				}
			} catch (error) {
				log.error("Error fetching POS Profile item groups", error)
				profileItemGroups.value = []
			}
		} else {
			profileItemGroups.value = []
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
