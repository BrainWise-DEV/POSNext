/**
 * D-R4-02 review I-3: with the worker down and the browser still "online" (a LAN whose
 * internet is down: navigator.onLine stays true), the till finds out the server is
 * unreachable by itself, so checkout takes the offline path and the sale is queued.
 *
 * A characterisation test: it passes on the branch it was written for. The page's own
 * network monitor (offlineState, started when the module loads, not by the worker)
 * pings the server at once and marks it offline on the first failure.
 * @vitest-environment jsdom
 */
import { afterAll, describe, expect, it, vi } from "vitest"

const queued = vi.hoisted(() => {
	class DeadWorker {
		constructor() {
			setTimeout(() => this.onerror?.({ message: "Worker error" }), 0)
		}
		postMessage() {}
		terminate() {}
	}
	globalThis.Worker = DeadWorker
	// The server is unreachable; the browser says it is online
	globalThis.fetch = () => Promise.reject(new TypeError("Failed to fetch"))
	return []
})
vi.mock("../mainThreadReads", () => ({
	queueInvoice: vi.fn(async (invoice) => {
		queued.push(invoice)
		return { success: true, id: 1, offline_id: "pos_offline_1" }
	}),
}))

vi.useFakeTimers()
const { offlineWorker } = await import("../workerClient")
const { isOffline } = await import("../offlineState")

afterAll(() => vi.useRealTimers())

describe("worker down, server unreachable, navigator.onLine true (review I-3)", () => {
	it("the till goes offline and the sale is queued", async () => {
		expect(navigator.onLine).toBe(true)
		expect(isOffline()).toBe(false)

		await vi.advanceTimersByTimeAsync(20000)
		expect(isOffline()).toBe(true)

		const sale = { items: [{ item_code: "A", qty: 1 }] }
		const saving = offlineWorker.saveOfflineInvoice(sale)
		await vi.advanceTimersByTimeAsync(20000)
		expect(await saving).toMatchObject({ success: true })
		expect(queued).toEqual([sale])
	})
})
