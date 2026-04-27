import { call } from "@/utils/apiWrapper"
import { db, getSetting, setSetting } from "./db"
import { offlineState } from "./offlineState"

// Cache structure definition - modify this when cache structure changes
const CACHE_STRUCTURE = {
	// Define what gets cached
	items: ["item_code", "item_name", "item_group", "barcodes", "price", "stock"],
	customers: ["name", "customer_name", "mobile_no", "email_id"],
	item_prices: ["price_list", "item_code", "price"],
	local_stock: ["item_code", "warehouse", "actual_qty"],
	payment_methods: [
		"mode_of_payment",
		"pos_profile",
		"default",
		"allow_in_returns",
		"type",
	],
}

// Generate cache version from structure hash
function getCacheStructureHash(structure) {
	const structureString = JSON.stringify(structure)
	let hash = 0
	for (let i = 0; i < structureString.length; i++) {
		const char = structureString.charCodeAt(i)
		hash = (hash << 5) - hash + char
		hash = hash & hash
	}
	return Math.abs(hash)
}

// Auto-increment cache version based on structure changes
function getCacheVersion() {
	const structureHash = getCacheStructureHash(CACHE_STRUCTURE)
	const storedHash = localStorage.getItem("pos_next_cache_structure_hash")
	const storedVersion = Number.parseInt(
		localStorage.getItem("pos_next_cache_version") || "1",
	)

	if (storedHash !== structureHash.toString()) {
		const newVersion = storedVersion + 1
		console.log(
			`Cache structure changed. Upgrading from v${storedVersion} to v${newVersion}`,
		)
		localStorage.setItem(
			"pos_next_cache_structure_hash",
			structureHash.toString(),
		)
		localStorage.setItem("pos_next_cache_version", newVersion.toString())
		return newVersion
	}

	return storedVersion
}

export const CACHE_VERSION = getCacheVersion()

// In-memory cache for fast access
export const memory = {
	// Offline queues
	offline_invoices: [],
	offline_customers: [],
	offline_payments: [],

	// Cached data
	items: [],
	customers: [],
	item_prices: {},
	local_stock: {},
	payment_methods: [],

	// Metadata
	items_last_sync: null,
	customers_last_sync: null,
	payment_methods_last_sync: null,
	cache_ready: false,
	stock_cache_ready: false,
	manual_offline: false,

	// Cache version
	cache_version: CACHE_VERSION,
}

// Initialize memory cache from IndexedDB
export const initMemoryCache = async () => {
	try {
		console.log("Initializing memory cache...")

		// Load cache version
		const storedVersion = await getSetting("cache_version", CACHE_VERSION)
		if (storedVersion !== CACHE_VERSION) {
			console.log("Cache version mismatch, clearing cache...")
			await clearAllCache()
			await setSetting("cache_version", CACHE_VERSION)
			memory.cache_version = CACHE_VERSION
		}

		// Load items last sync timestamp
		memory.items_last_sync = await getSetting("items_last_sync", null)
		memory.customers_last_sync = await getSetting("customers_last_sync", null)
		memory.cache_ready = await getSetting("cache_ready", false)
		memory.stock_cache_ready = await getSetting("stock_cache_ready", false)
		memory.manual_offline = await getSetting("manual_offline", false)

		// Sync manual_offline to centralized state manager
		if (memory.manual_offline) {
			offlineState.setManualOffline(true, { silent: true })
		}

		// Load items count (don't load all items into memory, too heavy)
		const itemsCount = await db.items.count()
		const customersCount = await db.customers.count()

		console.log(
			`Cache initialized: ${itemsCount} items, ${customersCount} customers`,
		)
		console.log(
			`Cache ready: ${memory.cache_ready}, Stock ready: ${memory.stock_cache_ready}`,
		)

		return true
	} catch (error) {
		console.error("Failed to initialize memory cache:", error)
		return false
	}
}

// Check if cache is ready for offline use
export const isCacheReady = () => {
	return memory.cache_ready
}

// Check if stock cache is ready
export const isStockCacheReady = () => {
	return memory.stock_cache_ready
}

// Get manual offline state (uses centralized offlineState)
export const isManualOffline = () => {
	return offlineState.manualOffline
}

// Set manual offline state (uses centralized offlineState)
export const setManualOffline = async (state) => {
	offlineState.setManualOffline(!!state)
	// Also persist to settings for worker initialization
	await setSetting("manual_offline", !!state)
	memory.manual_offline = !!state
}

// Toggle manual offline (uses centralized offlineState)
export const toggleManualOffline = async () => {
	const newState = offlineState.toggleManualOffline()
	await setSetting("manual_offline", newState)
	memory.manual_offline = newState
	return newState
}

// Load items from server (returns data for worker to cache)
export const cacheItemsFromServer = async (posProfile) => {
	try {
		console.log("Fetching items from server...")

		const response = await call("pos_next.api.items.get_items", {
			pos_profile: posProfile,
			start: 0,
			limit: 9999, // Get all items
		})

		if (response.message && Array.isArray(response.message)) {
			const items = response.message

			// Process items to add searchable fields
			const processedItems = items.map((item) => ({
				...item,
				barcodes: item.item_barcode
					? Array.isArray(item.item_barcode)
						? item.item_barcode.map((b) => b.barcode).filter(Boolean)
						: [item.item_barcode]
					: [],
			}))

			console.log(`Fetched ${processedItems.length} items from server`)
			return { items: processedItems }
		}

		return { items: [] }
	} catch (error) {
		console.error("Error fetching items from server:", error)
		throw error
	}
}

// Load customers from server (returns data for worker to cache)
// Uses the offline-enriched endpoint that includes addresses, loyalty
// points, and wallet balance — falls back to the basic endpoint if the
// backend doesn't have the new method (older deploys).
export const cacheCustomersFromServer = async (
	posProfile,
	{ modifiedSince = null } = {},
) => {
	try {
		console.log("Fetching customers (offline payload) from server...")

		try {
			const response = await call(
				"pos_next.api.customers.get_customers_for_offline",
				{
					pos_profile: posProfile,
					modified_since: modifiedSince,
					limit: 0,
				},
			)
			const customers = response?.message ?? response ?? []
			if (Array.isArray(customers)) {
				console.log(`Fetched ${customers.length} customers (enriched)`)
				return { customers }
			}
		} catch (enrichedErr) {
			console.warn(
				"get_customers_for_offline unavailable, falling back to get_customers",
				enrichedErr,
			)
		}

		const response = await call("pos_next.api.customers.get_customers", {
			pos_profile: posProfile,
			start: 0,
			limit: 0,
		})

		const customers = response?.message ?? response ?? []
		if (Array.isArray(customers)) {
			console.log(`Fetched ${customers.length} customers (basic)`)
			return { customers }
		}

		return { customers: [] }
	} catch (error) {
		console.error("Error fetching customers from server:", error)
		throw error
	}
}

/**
 * Refresh extras (addresses, loyalty points, wallet) for a single customer
 * and patch the cached row. Best-effort — no-op when offline.
 */
export const refreshCustomerExtrasFromServer = async (
	customer,
	{ company = null } = {},
) => {
	if (!customer) return null
	try {
		const result = await call(
			"pos_next.api.customers.get_customer_offline_extras",
			{
				customer,
				company,
			},
		)
		const extras = result?.message ?? result
		if (!extras || typeof extras !== "object") return null

		const existing = (await db.customers.get(customer)) || { name: customer }
		const merged = {
			...existing,
			addresses: extras.addresses || [],
			loyalty_points: extras.loyalty_points || 0,
			wallet_balance: extras.wallet_balance || 0,
		}
		await db.customers.put(merged)
		return merged
	} catch (error) {
		console.warn(`Failed to refresh extras for customer ${customer}:`, error)
		return null
	}
}

// Search items in cache
export const searchCachedItems = async (searchTerm = "", limit = 50) => {
	try {
		if (!searchTerm) {
			return await db.items.limit(limit).toArray()
		}

		const term = searchTerm.toLowerCase()

		// Search by item code, name, or barcode
		const results = await db.items
			.where("item_code")
			.startsWithIgnoreCase(term)
			.or("item_name")
			.startsWithIgnoreCase(term)
			.or("barcodes")
			.equals(term)
			.limit(limit)
			.toArray()

		return results
	} catch (error) {
		console.error("Error searching cached items:", error)
		return []
	}
}

// Search customers in cache
export const searchCachedCustomers = async (searchTerm = "", limit = 50) => {
	try {
		if (!searchTerm) {
			return await db.customers.limit(limit).toArray()
		}

		const term = searchTerm.toLowerCase()

		// Search by name, mobile, or email
		const results = await db.customers
			.where("customer_name")
			.startsWithIgnoreCase(term)
			.or("mobile_no")
			.startsWithIgnoreCase(term)
			.or("email_id")
			.startsWithIgnoreCase(term)
			.limit(limit)
			.toArray()

		return results
	} catch (error) {
		console.error("Error searching cached customers:", error)
		return []
	}
}

// Get item from cache by code
export const getCachedItem = async (itemCode) => {
	try {
		return await db.items.get(itemCode)
	} catch (error) {
		console.error("Error getting cached item:", error)
		return null
	}
}

// Get customer from cache by name
export const getCachedCustomer = async (customerName) => {
	try {
		return await db.customers.get(customerName)
	} catch (error) {
		console.error("Error getting cached customer:", error)
		return null
	}
}

// Check if cache needs refresh (older than 24 hours)
export const needsCacheRefresh = () => {
	if (!memory.items_last_sync) return true

	const ONE_DAY = 24 * 60 * 60 * 1000
	const now = Date.now()
	return now - memory.items_last_sync > ONE_DAY
}

// Clear all cached data
export const clearAllCache = async () => {
	try {
		console.log("Clearing all cache...")

		// Clear IndexedDB tables
		await db.items.clear()
		await db.customers.clear()
		await db.item_prices.clear()
		await db.stock.clear()
		await db.sales_persons.clear()
		await db.taxes.clear()
		await db.uoms.clear()
		await db.item_groups.clear()
		await db.brands.clear()
		await db.loyalty_programs.clear()

		// Reset memory
		memory.items = []
		memory.customers = []
		memory.item_prices = {}
		memory.local_stock = {}
		memory.items_last_sync = null
		memory.customers_last_sync = null
		memory.cache_ready = false
		memory.stock_cache_ready = false

		// Update settings
		await setSetting("items_last_sync", null)
		await setSetting("customers_last_sync", null)
		await setSetting("cache_ready", false)
		await setSetting("stock_cache_ready", false)

		console.log("Cache cleared successfully")
		return true
	} catch (error) {
		console.error("Error clearing cache:", error)
		return false
	}
}

// Get cache stats
export const getCacheStats = async () => {
	try {
		const itemsCount = await db.items.count()
		const customersCount = await db.customers.count()
		const queuedInvoices = await db.invoice_queue
			.filter((inv) => inv.synced === false)
			.count()

		return {
			items: itemsCount,
			customers: customersCount,
			queuedInvoices,
			cacheReady: memory.cache_ready,
			stockReady: memory.stock_cache_ready,
			lastSync: memory.items_last_sync
				? new Date(memory.items_last_sync).toLocaleString()
				: "Never",
		}
	} catch (error) {
		console.error("Error getting cache stats:", error)
		return {
			items: 0,
			customers: 0,
			queuedInvoices: 0,
			cacheReady: false,
			stockReady: false,
			lastSync: "Error",
		}
	}
}

/**
 * Cache payment methods from server
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<object>} - Result with payment methods array
 */
export async function cachePaymentMethodsFromServer(posProfile) {
	try {
		const result = await call("pos_next.api.pos_profile.get_payment_methods", {
			pos_profile: posProfile,
		})
		const paymentMethods = result?.message || result || []

		// Add pos_profile to each method for indexing
		const methodsWithProfile = paymentMethods.map((method) => ({
			...method,
			pos_profile: posProfile,
		}))

		// Store in IndexedDB
		await db.payment_methods.bulkPut(methodsWithProfile)

		// Update last sync timestamp
		const timestamp = Date.now()
		await setSetting("payment_methods_last_sync", timestamp)
		memory.payment_methods_last_sync = timestamp

		console.log(
			`Cached ${paymentMethods.length} payment methods for ${posProfile}`,
		)

		return { payment_methods: paymentMethods }
	} catch (error) {
		console.error("Error caching payment methods:", error)
		throw error
	}
}

/**
 * Get cached payment methods for a POS Profile
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<Array>} - Array of payment methods
 */
export async function getCachedPaymentMethods(posProfile) {
	try {
		const methods = await db.payment_methods
			.where("pos_profile")
			.equals(posProfile)
			.toArray()

		return methods
	} catch (error) {
		console.error("Error getting cached payment methods:", error)
		return []
	}
}

/**
 * Cache sales persons from server for offline use
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<object>} - Result with sales_persons array
 */
export async function cacheSalesPersonsFromServer(posProfile) {
	try {
		const result = await call("pos_next.api.pos_profile.get_sales_persons", {
			pos_profile: posProfile,
		})
		const salesPersons = result?.message || result || []

		// Add pos_profile to each person for indexing
		const personsWithProfile = salesPersons.map((person) => ({
			...person,
			pos_profile: posProfile,
		}))

		// Store in IndexedDB
		await db.sales_persons.bulkPut(personsWithProfile)

		// Update last sync timestamp
		const timestamp = Date.now()
		await setSetting("sales_persons_last_sync", timestamp)

		console.log(`Cached ${salesPersons.length} sales persons for ${posProfile}`)

		return { sales_persons: salesPersons }
	} catch (error) {
		console.error("Error caching sales persons:", error)
		throw error
	}
}

/**
 * Get cached sales persons for a POS Profile
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<Array>} - Array of sales persons
 */
export async function getCachedSalesPersons(posProfile) {
	try {
		const persons = await db.sales_persons
			.where("pos_profile")
			.equals(posProfile)
			.toArray()

		return persons
	} catch (error) {
		console.error("Error getting cached sales persons:", error)
		return []
	}
}

/**
 * Cache Sales Taxes & Charges Templates from server.
 *
 * Stores the full child-table breakdown so the frontend can apply taxes
 * offline. One round-trip; tagged with pos_profile so multiple profiles
 * can coexist in the same DB.
 */
export async function cacheTaxesFromServer(
	posProfile,
	{ company = null } = {},
) {
	try {
		const result = await call("pos_next.api.offline_data.get_taxes", {
			pos_profile: posProfile,
			company,
		})
		const taxes = result?.message ?? result ?? []
		if (!Array.isArray(taxes)) return { taxes: [] }

		const tagged = taxes.map((t) => ({ ...t, pos_profile: posProfile }))
		await db.taxes.bulkPut(tagged)
		await setSetting("taxes_last_sync", Date.now())
		console.log(`Cached ${tagged.length} tax templates for ${posProfile}`)
		return { taxes: tagged }
	} catch (error) {
		console.error("Error caching taxes:", error)
		throw error
	}
}

export async function getCachedTaxes(posProfile) {
	try {
		if (!posProfile) return await db.taxes.toArray()
		return await db.taxes.where("pos_profile").equals(posProfile).toArray()
	} catch (error) {
		console.error("Error reading cached taxes:", error)
		return []
	}
}

/**
 * Cache UOM list from server.
 */
export async function cacheUomsFromServer() {
	try {
		const result = await call("pos_next.api.offline_data.get_uoms")
		const uoms = result?.message ?? result ?? []
		if (!Array.isArray(uoms)) return { uoms: [] }

		await db.uoms.bulkPut(uoms)
		await setSetting("uoms_last_sync", Date.now())
		console.log(`Cached ${uoms.length} UOMs`)
		return { uoms }
	} catch (error) {
		console.error("Error caching UOMs:", error)
		throw error
	}
}

export async function getCachedUoms() {
	try {
		return await db.uoms.toArray()
	} catch (error) {
		console.error("Error reading cached UOMs:", error)
		return []
	}
}

/**
 * Cache Loyalty Programs (with collection rules) from server.
 */
export async function cacheLoyaltyProgramsFromServer({ company = null } = {}) {
	try {
		const result = await call(
			"pos_next.api.offline_data.get_loyalty_programs",
			{
				company,
			},
		)
		const programs = result?.message ?? result ?? []
		if (!Array.isArray(programs)) return { loyalty_programs: [] }

		await db.loyalty_programs.bulkPut(programs)
		await setSetting("loyalty_programs_last_sync", Date.now())
		console.log(`Cached ${programs.length} loyalty programs`)
		return { loyalty_programs: programs }
	} catch (error) {
		console.error("Error caching loyalty programs:", error)
		throw error
	}
}

export async function getCachedLoyaltyPrograms() {
	try {
		return await db.loyalty_programs.toArray()
	} catch (error) {
		console.error("Error reading cached loyalty programs:", error)
		return []
	}
}

/**
 * Cache item groups + brands lists from server (for offline filter dropdowns).
 */
export async function cacheItemGroupsFromServer(posProfile) {
	try {
		const result = await call("pos_next.api.items.get_item_groups", {
			pos_profile: posProfile,
		})
		const groups = result?.message ?? result ?? []
		if (!Array.isArray(groups)) return { item_groups: [] }

		await db.item_groups.bulkPut(groups)
		await setSetting("item_groups_last_sync", Date.now())
		console.log(`Cached ${groups.length} item groups`)
		return { item_groups: groups }
	} catch (error) {
		console.error("Error caching item groups:", error)
		throw error
	}
}

export async function getCachedItemGroups() {
	try {
		return await db.item_groups.toArray()
	} catch (error) {
		console.error("Error reading cached item groups:", error)
		return []
	}
}

export async function cacheBrandsFromServer(posProfile) {
	try {
		const result = await call("pos_next.api.items.get_brands", {
			pos_profile: posProfile,
		})
		const brands = result?.message ?? result ?? []
		if (!Array.isArray(brands)) return { brands: [] }

		await db.brands.bulkPut(brands)
		await setSetting("brands_last_sync", Date.now())
		console.log(`Cached ${brands.length} brands`)
		return { brands }
	} catch (error) {
		console.error("Error caching brands:", error)
		throw error
	}
}

export async function getCachedBrands() {
	try {
		return await db.brands.toArray()
	} catch (error) {
		console.error("Error reading cached brands:", error)
		return []
	}
}

/**
 * One-shot reference-data bootstrap: taxes + UOMs + loyalty in a single
 * round-trip. Falls back to per-endpoint caching if the bundle endpoint
 * is unavailable (older deploys).
 */
export async function cacheOfflineBundleFromServer(
	posProfile,
	{ company = null } = {},
) {
	try {
		const result = await call("pos_next.api.offline_data.get_offline_bundle", {
			pos_profile: posProfile,
			company,
		})
		const bundle = result?.message ?? result ?? {}

		const promises = []
		if (Array.isArray(bundle.taxes)) {
			const tagged = bundle.taxes.map((t) => ({
				...t,
				pos_profile: posProfile,
			}))
			promises.push(db.taxes.bulkPut(tagged))
		}
		if (Array.isArray(bundle.uoms)) {
			promises.push(db.uoms.bulkPut(bundle.uoms))
		}
		if (Array.isArray(bundle.loyalty_programs)) {
			promises.push(db.loyalty_programs.bulkPut(bundle.loyalty_programs))
		}
		await Promise.all(promises)

		const now = Date.now()
		await Promise.all([
			setSetting("taxes_last_sync", now),
			setSetting("uoms_last_sync", now),
			setSetting("loyalty_programs_last_sync", now),
		])

		return bundle
	} catch (error) {
		console.warn(
			"Bundle endpoint unavailable, falling back to per-endpoint:",
			error,
		)
		// Fallback: call endpoints individually.
		const [taxes, uoms, loyalty_programs] = await Promise.all([
			cacheTaxesFromServer(posProfile, { company }).catch(() => ({
				taxes: [],
			})),
			cacheUomsFromServer().catch(() => ({ uoms: [] })),
			cacheLoyaltyProgramsFromServer({ company }).catch(() => ({
				loyalty_programs: [],
			})),
		])
		return {
			taxes: taxes.taxes || [],
			uoms: uoms.uoms || [],
			loyalty_programs: loyalty_programs.loyalty_programs || [],
		}
	}
}

// Initialize cache on import
initMemoryCache()
