import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const consumeCachedSerials = vi.fn(async () => {})
const returnCachedSerials = vi.fn(async () => {})

vi.mock("@/utils/offline/items", () => ({
	consumeCachedSerials,
	returnCachedSerials,
	persistItemBatchSerialData: vi.fn(async () => true),
}))
vi.mock("@/utils/apiWrapper", () => ({ call: vi.fn() }))

const { useSerialNumberStore } = await import("../serialNumber")

describe("serialNumber offline durable cache", () => {
	beforeEach(() => {
		setActivePinia(createPinia())
		consumeCachedSerials.mockClear()
		returnCachedSerials.mockClear()
	})

	it("consumes from the durable cache when the in-memory cache is empty", () => {
		useSerialNumberStore().consumeSerials("SER-1", "SN-1")
		expect(consumeCachedSerials).toHaveBeenCalledWith("SER-1", "SN-1")
	})

	it("returns to the durable cache with the dialog warehouse", () => {
		const store = useSerialNumberStore()
		store.setWarehouse("Stores - _TC")
		store.returnSerials("SER-1", "SN-1")
		expect(returnCachedSerials).toHaveBeenCalledWith(
			"SER-1",
			"SN-1",
			"Stores - _TC",
		)
	})
})
