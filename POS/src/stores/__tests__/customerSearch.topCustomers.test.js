import { beforeEach, describe, expect, it, vi } from "vitest"
import { createPinia, setActivePinia } from "pinia"

// The store wires up a realtime socket listener and an offline worker at
// setup time; neither is relevant to the ordering logic under test.
vi.mock("@/composables/useRealtimeCustomers", () => ({
	useRealtimeCustomers: () => ({ onCustomerUpdate: () => {} }),
}))
vi.mock("@/utils/offline/workerClient", () => ({
	offlineWorker: {
		searchCachedCustomers: vi.fn(),
		cacheCustomers: vi.fn(),
		deleteCustomers: vi.fn(),
	},
}))
vi.mock("@/utils/offline", () => ({ isOffline: () => false }))
vi.mock("@/utils/apiWrapper", () => ({ call: vi.fn() }))

import { useCustomerSearchStore } from "@/stores/customerSearch"

const cust = (name, customer_name) => ({ name, customer_name })

describe("customerSearch store — topCustomers", () => {
	beforeEach(() => {
		setActivePinia(createPinia())
		localStorage.clear()
	})

	it("returns customers ranked by selection count (desc)", () => {
		const store = useCustomerSearchStore()
		store.allCustomers = [
			cust("C-ZED", "Zed"),
			cust("C-BETA", "Beta"),
			cust("C-ALPHA", "Alpha"),
		]
		store.trackCustomerSelection("C-ZED")
		store.trackCustomerSelection("C-ZED")
		store.trackCustomerSelection("C-ZED")
		store.trackCustomerSelection("C-BETA")

		expect(store.topCustomers.map((c) => c.name)).toEqual(["C-ZED", "C-BETA"])
	})

	it("breaks count ties alphabetically by customer_name", () => {
		const store = useCustomerSearchStore()
		store.allCustomers = [cust("C-1", "Beta"), cust("C-2", "Alpha")]
		store.trackCustomerSelection("C-1")
		store.trackCustomerSelection("C-2")

		expect(store.topCustomers.map((c) => c.name)).toEqual(["C-2", "C-1"])
	})

	it("caps the list at 5 entries", () => {
		const store = useCustomerSearchStore()
		store.allCustomers = Array.from({ length: 8 }, (_, i) =>
			cust(`C-${i}`, `Name ${i}`),
		)
		// Give each a descending, distinct count so order is deterministic.
		for (let i = 0; i < 8; i++) {
			for (let n = 0; n <= 8 - i; n++) store.trackCustomerSelection(`C-${i}`)
		}

		expect(store.topCustomers).toHaveLength(5)
		expect(store.topCustomers.map((c) => c.name)).toEqual([
			"C-0",
			"C-1",
			"C-2",
			"C-3",
			"C-4",
		])
	})

	it("ignores IDs that are not present in allCustomers", () => {
		const store = useCustomerSearchStore()
		store.allCustomers = [cust("C-ALPHA", "Alpha")]
		store.trackCustomerSelection("C-GHOST") // not in allCustomers
		store.trackCustomerSelection("C-ALPHA")

		expect(store.topCustomers.map((c) => c.name)).toEqual(["C-ALPHA"])
	})

	it("persists counts to localStorage and reloads them", () => {
		const store = useCustomerSearchStore()
		store.allCustomers = [cust("C-ALPHA", "Alpha")]
		store.trackCustomerSelection("C-ALPHA")
		store.trackCustomerSelection("C-ALPHA")

		expect(JSON.parse(localStorage.getItem("pos_customer_counts"))).toEqual({
			"C-ALPHA": 2,
		})

		// Fresh store instance loads persisted counts via loadCustomerHistory().
		setActivePinia(createPinia())
		const store2 = useCustomerSearchStore()
		store2.allCustomers = [cust("C-ALPHA", "Alpha")]
		store2.loadCustomerHistory()
		expect(store2.customerCounts).toEqual({ "C-ALPHA": 2 })
		expect(store2.topCustomers.map((c) => c.name)).toEqual(["C-ALPHA"])
	})
})
