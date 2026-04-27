/**
 * Tests the offline barcode-scan fallback path added to the itemSearch
 * store. Specifically:
 *   - When offline, we go straight to the worker cache (no server call).
 *   - When online and server returns nothing, we still try the cache.
 *   - When online and server errors, we fall back to the cache and only
 *     re-throw if the cache is empty too.
 */

import { setActivePinia, createPinia } from "pinia"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const isOfflineMock = vi.fn()
const searchCachedItemsMock = vi.fn()
const submitMock = vi.fn()

vi.mock("@/utils/offline", () => ({
	isOffline: () => isOfflineMock(),
}))

vi.mock("@/utils/offline/workerClient", () => ({
	offlineWorker: {
		searchCachedItems: (...args) => searchCachedItemsMock(...args),
		// Stubs for other accesses the store may make:
		isCacheReady: vi.fn().mockResolvedValue(false),
		setShowVariantsAsItems: vi.fn(),
		removeItemsByGroups: vi.fn(),
		cacheItems: vi.fn(),
		clearItemsCache: vi.fn(),
		searchCachedItemsByGroup: vi.fn().mockResolvedValue([]),
		getCacheStats: vi.fn().mockResolvedValue({}),
		cacheSalesPersons: vi.fn(),
	},
}))

vi.mock("frappe-ui", () => ({
	createResource: ({ url }) => ({
		url,
		submit: (...args) => submitMock(url, ...args),
		reload: vi.fn(),
		data: null,
		loading: false,
	}),
}))

vi.mock("@/utils/apiWrapper", () => ({ call: vi.fn() }))

// useItemSearchStore imports settings via posSettings — keep that store's
// default profile so `posProfile.value` is set.
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({
		posProfile: { value: "PROFILE-X" },
		posProfileDetails: { value: { warehouse: "WH-Main" } },
		showVariantsAsItems: false,
	}),
}))

describe("itemSearch.searchByBarcode offline fallback", () => {
	beforeEach(() => {
		setActivePinia(createPinia())
		isOfflineMock.mockReset()
		searchCachedItemsMock.mockReset()
		submitMock.mockReset()
	})

	afterEach(() => {
		vi.clearAllMocks()
	})

	const loadStore = async () => {
		// Lazy import so the mocks above are in place.
		const mod = await import("@/stores/itemSearch")
		const store = mod.useItemSearchStore()
		store.posProfile = "PROFILE-X"
		return store
	}

	it("uses the cache directly when offline (no server call)", async () => {
		isOfflineMock.mockReturnValue(true)
		searchCachedItemsMock.mockResolvedValue([
			{ item_code: "ITEM-A", item_name: "Apple", barcodes: ["8901234567890"] },
		])
		const store = await loadStore()

		const item = await store.searchByBarcode("8901234567890")

		expect(item?.item_code).toBe("ITEM-A")
		expect(submitMock).not.toHaveBeenCalled()
		expect(searchCachedItemsMock).toHaveBeenCalledWith("8901234567890", 1)
	})

	it("returns null cleanly when offline cache misses", async () => {
		isOfflineMock.mockReturnValue(true)
		searchCachedItemsMock.mockResolvedValue([])
		const store = await loadStore()

		expect(await store.searchByBarcode("999")).toBeNull()
	})

	it("falls back to cache when the server errors while online", async () => {
		isOfflineMock.mockReturnValue(false)
		submitMock.mockRejectedValue(new Error("HTTP 500"))
		searchCachedItemsMock.mockResolvedValue([
			{ item_code: "ITEM-B", item_name: "Banana", barcodes: ["8909876543210"] },
		])
		const store = await loadStore()

		const item = await store.searchByBarcode("8909876543210")
		expect(item?.item_code).toBe("ITEM-B")
	})

	it("re-throws when both server and cache fail", async () => {
		isOfflineMock.mockReturnValue(false)
		submitMock.mockRejectedValue(new Error("server boom"))
		searchCachedItemsMock.mockResolvedValue([])
		const store = await loadStore()

		await expect(store.searchByBarcode("nope")).rejects.toThrow(/server boom/)
	})
})
