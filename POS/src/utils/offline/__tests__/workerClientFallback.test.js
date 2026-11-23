/**
 * D-R4-02: when the offline worker cannot start (e.g. its script is not reachable on an
 * offline reload), its reads are answered from IndexedDB on the page. Before, the
 * fallback answered "nothing cached": an empty item grid, "No payment methods
 * available" and no offers, although all were cached.
 */
import { beforeEach, describe, expect, it, vi } from "vitest"

const reads = vi.hoisted(() => ({
	cachedPaymentMethods: vi.fn(async () => [{ mode_of_payment: "Cash", pos_profile: "P1" }]),
	cachedOffers: vi.fn(async () => [{ name: "PR-1", pos_profile: "P1" }]),
	cachedItemCount: vi.fn(async () => 15),
	cacheStats: vi.fn(async () => ({ items: 15, customers: 3, queuedInvoices: 0, cacheReady: true, lastSync: 1 })),
	searchItems: vi.fn(async () => [{ item_code: "A" }]),
	searchItemsByGroup: vi.fn(async () => [{ item_code: "B" }]),
	searchCustomers: vi.fn(async () => [{ name: "CUST-1" }]),
	queuedInvoiceCount: vi.fn(async () => 2),
	queuedInvoices: vi.fn(async () => [{ offline_id: "a" }, { offline_id: "b" }]),
	queueInvoice: vi.fn(async () => ({ success: true, id: 7, offline_id: "pos_offline_x" })),
}))
vi.mock("../mainThreadReads", () => reads)

const { offlineWorker } = await import("../workerClient")

describe("worker unavailable: reads come from the page's IndexedDB", () => {
	beforeEach(() => {
		offlineWorker.workerCrashed = true
		offlineWorker.initAttempts = offlineWorker.maxInitAttempts
	})

	it("payment methods", async () => {
		expect(await offlineWorker.getCachedPaymentMethods("P1")).toEqual([{ mode_of_payment: "Cash", pos_profile: "P1" }])
		expect(reads.cachedPaymentMethods).toHaveBeenCalledWith("P1")
	})

	it("offers", async () => {
		expect((await offlineWorker.getCachedOffers("P1")).map((o) => o.name)).toEqual(["PR-1"])
	})

	it("cache stats and readiness, so the item grid loads from the cache", async () => {
		expect((await offlineWorker.getCacheStats()).cacheReady).toBe(true)
		expect(await offlineWorker.isCacheReady()).toBe(true)
	})

	it("item search, in the display mode the worker was told", async () => {
		await offlineWorker.setShowVariantsAsItems(true)
		expect(await offlineWorker.searchCachedItems("", 20, 0)).toEqual([{ item_code: "A" }])
		expect(reads.searchItems).toHaveBeenCalledWith("", 20, 0, true)
		expect(await offlineWorker.searchCachedItemsByGroup(["G"], 20, 0)).toEqual([{ item_code: "B" }])
	})
})

describe("worker unavailable: an offline sale is still taken", () => {
	beforeEach(() => {
		offlineWorker.workerCrashed = true
		offlineWorker.initAttempts = offlineWorker.maxInitAttempts
	})

	it("the sale is queued from the page and counted", async () => {
		const sale = { items: [{ item_code: "A", qty: 1 }] }
		expect(await offlineWorker.saveOfflineInvoice(sale)).toEqual({ success: true, id: 7, offline_id: "pos_offline_x" })
		expect(reads.queueInvoice).toHaveBeenCalledWith(sale)
		expect(await offlineWorker.getOfflineInvoiceCount()).toBe(2)
	})

	it("the pending list matches the pending count (review M1)", async () => {
		expect((await offlineWorker.getOfflineInvoices()).length).toBe(await offlineWorker.getOfflineInvoiceCount())
	})

	it("customers are searched from the page", async () => {
		expect(await offlineWorker.searchCachedCustomers("cu", 5)).toEqual([{ name: "CUST-1" }])
		expect(reads.searchCustomers).toHaveBeenCalledWith("cu", 5)
	})
})

describe("worker crashing with reads in flight", () => {
	it("answers a pending read from the page instead of failing it", async () => {
		offlineWorker.workerCrashed = false
		const pending = new Promise((resolve, reject) =>
			offlineWorker.pendingMessages.set(99, {
				resolve,
				reject,
				messageType: "GET_PAYMENT_METHODS",
				payload: { posProfile: "P1" },
			})
		)
		offlineWorker.rejectAllPending("Worker crashed: Worker error")
		expect(await pending).toEqual([{ mode_of_payment: "Cash", pos_profile: "P1" }])
	})

	it("a crashed worker that will restart still answers reads at once", async () => {
		offlineWorker.workerCrashed = true
		offlineWorker.initAttempts = 0
		offlineWorker.worker = null
		const started = Date.now()
		expect((await offlineWorker.getCacheStats()).cacheReady).toBe(true)
		expect(Date.now() - started).toBeLessThan(1000)
	})
})
