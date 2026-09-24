// @vitest-environment jsdom
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const call = vi.fn(async () => [
	{ name: "C1", customer_name: "C1", disabled: 0 },
])

vi.mock("@/utils/apiWrapper", () => ({ call }))
vi.mock("@/utils/offline", () => ({ isOffline: () => false }))
vi.mock("@/utils/offline/workerClient", () => ({
	offlineWorker: {
		searchCachedCustomers: vi.fn(async () => []),
		cacheCustomers: vi.fn(async () => {}),
		removeCustomers: vi.fn(async () => {}),
	},
}))
vi.mock("@/composables/useRealtimeCustomers", () => ({
	useRealtimeCustomers: () => ({
		onCustomerUpdate: vi.fn(),
		onCustomerDelete: vi.fn(),
	}),
}))

const { useCustomerSearchStore } = await import("../customerSearch")

describe("customerSearch loadAllCustomers", () => {
	beforeEach(() => {
		setActivePinia(createPinia())
		call.mockClear()
	})

	it("fetches everything when the cache is empty, ignoring a stale sync key", async () => {
		localStorage.setItem("pos_customers_last_sync", "2026-09-24T00:00:00.000Z")
		const store = useCustomerSearchStore()
		await store.loadAllCustomers("P1")
		expect(call.mock.calls[0][1].modified_since).toBeNull()
		expect(store.allCustomers.map((c) => c.name)).toEqual(["C1"])
	})
})
