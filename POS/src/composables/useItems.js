import { isOffline } from "@/utils/offline"
import { offlineWorker } from "@/utils/offline/workerClient"
import { createResource } from "frappe-ui"
import { computed, ref, toValue, watch } from "vue"

export function useItems(posProfile, cartItems = ref([])) {
	const items = ref([])
	const searchTerm = ref("")
	const selectedItemGroup = ref(null)
	const itemGroups = ref([])
	const loading = ref(false)

	// Resources (kept for server-side refresh when online)
	const itemsResource = createResource({
		url: "pos_next.api.items.get_items",
		makeParams() {
			return {
				pos_profile: toValue(posProfile),
				search_term: searchTerm.value || null,
				item_group: selectedItemGroup.value || null,
				start: 0,
				limit: 100,
			}
		},
		auto: false,
		onSuccess(data) {
			items.value = data?.message || data || []
		},
		onError(error) {
			console.error("Error fetching items:", error)
			items.value = []
		},
	})

	const itemGroupsResource = createResource({
		url: "pos_next.api.items.get_item_groups",
		makeParams() {
			return {
				pos_profile: toValue(posProfile),
			}
		},
		auto: false,
		onSuccess(data) {
			itemGroups.value = data?.message || data || []
		},
		onError(error) {
			console.error("Error fetching item groups:", error)
			itemGroups.value = []
		},
	})

	const searchByBarcodeResource = createResource({
		url: "pos_next.api.items.search_by_barcode",
		auto: false,
	})

	// Computed - items with adjusted stock based on cart
	const filteredItems = computed(() => {
		if (!items.value || items.value.length === 0) return []

		let filtered = items.value

		// Filter by search term (local filtering for faster response)
		if (searchTerm.value && searchTerm.value.length > 0) {
			const term = searchTerm.value.toLowerCase()
			filtered = filtered.filter(
				(item) =>
					item.item_name?.toLowerCase().includes(term) ||
					item.item_code?.toLowerCase().includes(term) ||
					item.barcode?.toLowerCase().includes(term),
			)
		}

		// Adjust stock quantities based on cart items
		return filtered.map((item) => {
			const cartItem = toValue(cartItems).find(
				(ci) => ci.item_code === item.item_code,
			)
			if (cartItem) {
				const originalStock = item.actual_qty || item.stock_qty || 0
				const availableStock = originalStock - cartItem.quantity
				return {
					...item,
					actual_qty: availableStock,
					stock_qty: availableStock,
					original_stock: originalStock,
				}
			}
			return item
		})
	})

	// Watch for search term changes and reload items
	let searchTimeout = null
	watch(searchTerm, (newVal) => {
		// Clear existing timeout
		if (searchTimeout) {
			clearTimeout(searchTimeout)
		}

		// Set new timeout for debounced search
		searchTimeout = setTimeout(() => {
			if (newVal && newVal.length >= 3) {
				// Check if it looks like a barcode (numbers only and length > 8)
				const isBarcode = /^\d{8,}$/.test(newVal)
				if (isBarcode) {
					searchByBarcode(newVal)
				} else {
					itemsResource.reload()
				}
			} else if (!newVal) {
				itemsResource.reload()
			}
		}, 300)
	})

	// Watch for item group changes and reload items
	watch(selectedItemGroup, () => {
		itemsResource.reload()
	})

	// Methods
	async function searchByBarcode(barcode) {
		try {
			const result = await searchByBarcodeResource.submit({
				barcode,
				pos_profile: posProfile,
			})
			return result?.message || result
		} catch (error) {
			console.error("Error searching by barcode:", error)
			return null
		}
	}

	function refreshItems() {
		itemsResource.reload()
	}

	function loadItemGroups() {
		itemGroupsResource.reload()
	}

	// Cache-first loading function using worker
	async function loadItems() {
		// Check if cache is ready using worker
		const cacheReady = await offlineWorker.isCacheReady()

		// If offline or cache is ready, use cache via worker
		if (isOffline() || cacheReady) {
			loading.value = true
			try {
				const cached = await offlineWorker.searchCachedItems(
					searchTerm.value,
					100,
				)
				items.value = cached || []
			} catch (error) {
				console.error("Error loading from cache:", error)
				items.value = []
			} finally {
				loading.value = false
			}
		} else {
			// If online and cache not ready, use server
			itemsResource.reload()
		}
	}

	// Get item by code (cache-first) using worker
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
			console.error("Error getting item:", error)
			return null
		}
	}

	// Check if cache is ready
	async function checkCacheReady() {
		return await offlineWorker.isCacheReady()
	}

	return {
		// State
		items,
		filteredItems,
		searchTerm,
		selectedItemGroup,
		itemGroups,
		loading,

		// Methods
		searchByBarcode,
		refreshItems,
		loadItemGroups,
		loadItems,
		getItem,
		checkCacheReady,

		// Resources
		itemsResource,
		itemGroupsResource,
		searchByBarcodeResource,

		// Offline helpers
		isOffline,
	}
}
