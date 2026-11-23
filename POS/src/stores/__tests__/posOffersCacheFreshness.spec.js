/**
 * D-R4-01: the offer list is not loaded once per page and trusted forever.
 * - the header Refresh fetches it again and rewrites the offline cache;
 * - an empty list from the server clears the cache (an ended offer is not kept);
 * - offline, a cached list older than POS Settings' validity (default 24 h) applies nothing.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? s.replace(/{(\d+)}/g, (m, n) => args[n]) : s)
})
const net = vi.hoisted(() => ({ offline: false, offers: [] }))
const worker = vi.hoisted(() => ({
	cached: [],
	// postMessage clones what it sends: a reactive Proxy cannot be cloned
	cacheOffers: vi.fn(async (...args) => {
		structuredClone(args)
		return { success: true }
	}),
	getCachedOffers: vi.fn(async () => worker.cached),
}))
const settings = vi.hoisted(() => ({ value: {} }))
vi.mock("@/utils/apiWrapper", () => ({ call: vi.fn(async () => net.offers) }))
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn() }),
}))
vi.mock("@/utils/offline", () => ({ isOffline: () => net.offline }))
vi.mock("@/utils/offline/workerClient", () => ({
	offlineWorker: {
		cacheOffers: (...a) => worker.cacheOffers(...a),
		getCachedOffers: (...a) => worker.getCachedOffers(...a),
	},
}))
vi.mock("@/utils/offline/db", () => ({
	getOneTimeRedemptions: vi.fn(),
	setOneTimeRedemptions: vi.fn(),
	addOneTimeRedemptions: vi.fn(),
}))
vi.mock("@/utils/offerStrategies", () => ({ loadOfferStrategyPlugins: vi.fn(async () => {}) }))
vi.mock("@/stores/posShift", () => ({ usePOSShiftStore: () => ({ currentProfile: {} }) }))
vi.mock("@/stores/posSettings", () => ({ usePOSSettingsStore: () => ({ settings: settings.value }) }))

const { usePOSOffersStore } = await import("../posOffers")

const HOUR = 3600 * 1000
const buy1 = { name: "PR-BUY1", title: "Buy one", auto: 1, apply_on: "Item Code", eligible_items: ["BUY50"], min_qty: 2 }
const cart = { itemCount: 2, itemCodes: ["BUY50"], subtotal: 100, itemQuantities: { BUY50: 2 } }

describe("D-R4-01: the offer list is kept fresh", () => {
	let offers
	beforeEach(() => {
		setActivePinia(createPinia())
		offers = usePOSOffersStore()
		net.offline = false
		net.offers = []
		worker.cached = []
		settings.value = {}
		worker.cacheOffers.mockClear()
		worker.getCachedOffers.mockClear()
	})

	it("Refresh fetches the list again and rewrites the cache", async () => {
		net.offers = [buy1]
		await offers.ensureOffersFetched("P")
		net.offers = []
		await offers.refreshOffers("P")
		expect(offers.availableOffers).toEqual([])
		expect(worker.cacheOffers).toHaveBeenLastCalledWith([], "P")
	})

	it("the list fetched online reaches the cache", async () => {
		net.offers = [buy1]
		await offers.ensureOffersFetched("P")
		await expect(worker.cacheOffers.mock.results.at(-1).value).resolves.toEqual({ success: true })
		expect(worker.cacheOffers).toHaveBeenLastCalledWith([buy1], "P")
	})

	it("an empty list from the server clears the cache", async () => {
		await offers.ensureOffersFetched("P")
		expect(worker.cacheOffers).toHaveBeenCalledWith([], "P")
	})

	it("offline, a list cached within 24 h is applied", async () => {
		net.offline = true
		worker.cached = [{ ...buy1, _cached_at: Date.now() - 23 * HOUR }]
		await offers.ensureOffersFetched("P")
		offers.updateCartSnapshot(cart)
		expect(offers.autoEligibleOffers.map((o) => o.name)).toEqual(["PR-BUY1"])
	})

	it("offline, a list cached more than 24 h ago is not applied", async () => {
		net.offline = true
		worker.cached = [{ ...buy1, _cached_at: Date.now() - 25 * HOUR }]
		await offers.ensureOffersFetched("P")
		offers.updateCartSnapshot(cart)
		expect(offers.autoEligibleOffers).toEqual([])
		expect(offers.checkOfferEligibility(buy1).reason).toContain("24")
	})

	it("the validity is POS Settings' offline_offer_validity_hours", async () => {
		settings.value = { offline_offer_validity_hours: 2 }
		net.offline = true
		worker.cached = [{ ...buy1, _cached_at: Date.now() - 3 * HOUR }]
		await offers.ensureOffersFetched("P")
		offers.updateCartSnapshot(cart)
		expect(offers.autoEligibleOffers).toEqual([])
	})

	it("a list the page fetched online goes stale offline too", async () => {
		vi.useFakeTimers({ toFake: ["Date"] })
		try {
			net.offers = [buy1]
			await offers.ensureOffersFetched("P")
			net.offline = true
			vi.setSystemTime(Date.now() + 25 * HOUR)
			offers.updateCartSnapshot(cart)
			expect(offers.autoEligibleOffers).toEqual([])
		} finally {
			vi.useRealTimers()
		}
	})
})

describe("D-R4-02: offers when the server does not answer", () => {
	let offers
	beforeEach(() => {
		setActivePinia(createPinia())
		offers = usePOSOffersStore()
		net.offline = false
		worker.cached = [{ ...buy1, _cached_at: Date.now() }]
		worker.cacheOffers.mockClear()
	})

	it("a failed online fetch serves the cached list, fetched again once the server answers", async () => {
		const { call } = await import("@/utils/apiWrapper")
		call.mockRejectedValueOnce(new TypeError("Failed to fetch"))
		await offers.ensureOffersFetched("P")
		expect(offers.availableOffers.map((o) => o.name)).toEqual(["PR-BUY1"])
		expect(offers.offersFromCache).toBe(true)

		expect(worker.cacheOffers).not.toHaveBeenCalled() // the failure did not clear the cache

		// A minute later the server answers (review M9: not before)
		vi.useFakeTimers({ toFake: ["Date"] })
		try {
			vi.setSystemTime(Date.now() + 61 * 1000)
			net.offers = []
			await offers.ensureOffersFetched("P")
			expect(offers.availableOffers).toEqual([])
			expect(offers.offersFromCache).toBe(false)
		} finally {
			vi.useRealTimers()
		}
	})

	it("an answer that is not a list is no list: the cache is kept (review I-2)", async () => {
		net.offers = { exc_type: "ServerError" }
		await offers.ensureOffersFetched("P")
		expect(worker.cacheOffers).not.toHaveBeenCalled()
		expect(offers.availableOffers.map((o) => o.name)).toEqual(["PR-BUY1"])
	})

	it("a failed fetch is not retried on every cart pass (review M9)", async () => {
		const { call } = await import("@/utils/apiWrapper")
		call.mockClear()
		call.mockRejectedValue(new TypeError("Failed to fetch"))
		try {
			await offers.ensureOffersFetched("P")
			await offers.ensureOffersFetched("P")
			await offers.ensureOffersFetched("P")
			expect(call).toHaveBeenCalledTimes(1)
			expect(offers.availableOffers.map((o) => o.name)).toEqual(["PR-BUY1"])
		} finally {
			call.mockReset()
			call.mockImplementation(async () => net.offers)
		}
	})

	it("Refresh still fetches at once after a failure", async () => {
		const { call } = await import("@/utils/apiWrapper")
		call.mockRejectedValueOnce(new TypeError("Failed to fetch"))
		await offers.ensureOffersFetched("P")
		net.offers = []
		await offers.refreshOffers("P")
		expect(offers.offersFromCache).toBe(false)
	})
})
