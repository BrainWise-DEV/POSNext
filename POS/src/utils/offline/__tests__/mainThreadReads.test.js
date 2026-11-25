/**
 * Review M1/M2: the main-thread fallback reports the real pending count in its cache
 * stats, and a sale the worker queued as it crashed is reported queued, not failed.
 */
import { describe, expect, it, vi } from "vitest"

const queue = vi.hoisted(() => ({ rows: [], addFails: false }))
vi.mock("../db", () => {
	const table = (name) => {
		if (name === "invoice_queue") {
			return {
				where: () => ({ equals: (id) => ({ first: async () => queue.rows.find((r) => r.offline_id === id) }) }),
				add: async (row) => {
					if (queue.addFails) {
						// The worker's add of the same sale committed first
						queue.rows.push({ ...row, id: 41 })
						throw Object.assign(new Error("Key already exists"), { name: "ConstraintError" })
					}
					queue.rows.push({ ...row, id: 42 })
					return 42
				},
			}
		}
		return {
			count: async () => (name === "items" ? 5 : 2),
			filter: () => ({ count: async () => 0 }),
			get: async () => null,
		}
	}
	return { db: { table } }
})
vi.mock("../sync", () => ({ getOfflineInvoiceCount: vi.fn(async () => 3), getOfflineInvoices: vi.fn(async () => []) }))

const reads = await import("../mainThreadReads")

describe("main-thread fallback reads", () => {
	it("cache stats carry the real pending count (M1)", async () => {
		expect((await reads.cacheStats()).queuedInvoices).toBe(3)
	})

	it("a sale the worker queued as it crashed is reported queued (M2)", async () => {
		queue.addFails = true
		const result = await reads.queueInvoice({ offline_id: "pos_offline_race", items: [{ item_code: "A" }] })
		expect(result).toMatchObject({ success: true, id: 41, duplicate: true })
	})
})
