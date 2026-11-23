/**
 * D-R4-02 review I-1: a worker that failed to start offline is started again when the
 * connection returns, so the offline cache is written again; a cache write lost while
 * it is down is announced, not swallowed.
 * @vitest-environment jsdom
 */
import { afterAll, describe, expect, it, vi } from "vitest"

const fake = vi.hoisted(() => {
	const state = { fail: true, created: 0, messages: [] }
	class FakeWorker {
		constructor() {
			state.created += 1
			this.failed = state.fail
			setTimeout(() => {
				if (this.failed) this.onerror?.({ message: "Worker error" })
				else this.onmessage?.({ data: { type: "WORKER_READY", payload: { serverOnline: true } } })
			}, 0)
		}
		postMessage(message) {
			state.messages.push(message.type)
			setTimeout(() => this.onmessage?.({ data: { type: "SUCCESS", id: message.id, payload: { success: true, count: 1 } } }), 0)
		}
		terminate() {}
	}
	globalThis.Worker = FakeWorker
	return state
})

vi.useFakeTimers()
const { offlineWorker, CACHE_WRITE_FAILED_EVENT } = await import("../workerClient")
const { offlineState } = await import("../offlineState")

afterAll(() => vi.useRealTimers())

describe("worker revive (review I-1)", () => {
	it("3 failed starts, then a reconnect: a live worker and a cache write that succeeds", async () => {
		// Import started attempt 1; the client restarts it twice more, then gives up
		await vi.advanceTimersByTimeAsync(30000)
		expect(fake.created).toBe(3)
		expect(offlineWorker.workerCrashed).toBe(true)

		// Down: the write fails, and says so
		const failed = vi.fn()
		window.addEventListener(CACHE_WRITE_FAILED_EVENT, failed)
		const lost = offlineWorker.cacheOffers([{ name: "PR-1" }], "P1").catch((error) => error)
		await vi.advanceTimersByTimeAsync(30000)
		expect((await lost).message).toContain("Worker unavailable")
		expect(failed).toHaveBeenCalled()

		// The connection comes back and the worker script is reachable again
		fake.fail = false
		const before = fake.created
		offlineState.updateState({ serverOnline: false })
		await vi.advanceTimersByTimeAsync(500)
		offlineState.updateState({ serverOnline: true })
		await vi.advanceTimersByTimeAsync(500)

		expect(fake.created).toBe(before + 1) // a new worker, started by the reconnect
		expect(offlineWorker.ready).toBe(true)
		expect(offlineWorker.workerCrashed).toBe(false)
		const written = offlineWorker.cacheOffers([{ name: "PR-1" }], "P1")
		await vi.advanceTimersByTimeAsync(10)
		expect(await written).toEqual({ success: true, count: 1 })
		expect(fake.messages).toContain("CACHE_OFFERS")
	})
})
