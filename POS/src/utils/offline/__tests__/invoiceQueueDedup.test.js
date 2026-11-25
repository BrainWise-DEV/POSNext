/**
 * Ruling 136 (d): an offline sale carries the cart's offline_id, so paying a restored
 * cart again (after a crash between the queue write and the cart clear) queues no
 * second invoice, and the server's offline_id dedup covers one already synced.
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/utils/apiWrapper", () => ({ call: vi.fn() }))
vi.mock("@/utils/offline/offlineState", () => ({
	offlineState: { isOffline: true, setServerOnline: vi.fn() },
}))

const rows = new Map()
let nextId = 1

vi.mock("@/utils/offline/db", () => {
	const invoice_queue = {
		async add(row) {
			if ([...rows.values()].some((r) => r.offline_id === row.offline_id)) {
				throw new Error("ConstraintError")
			}
			const id = nextId++
			rows.set(id, { ...row, id })
			return id
		},
		where(field) {
			return {
				equals(value) {
					return {
						async first() {
							return [...rows.values()].find((r) => r[field] === value) || undefined
						},
					}
				},
			}
		},
	}
	return {
		db: { invoice_queue, stock: { get: async () => null, put: async () => {} } },
		getSetting: async () => null,
		setSetting: async () => true,
	}
})

const { saveOfflineInvoice } = await import("@/utils/offline/sync")
const { queuedOfflineId } = await import("@/utils/offline/uuid")

const invoice = (extra = {}) => ({ items: [{ item_code: "A", qty: 1 }], ...extra })

describe("offline invoice queue: the cart's offline_id is reused", () => {
	beforeEach(() => {
		rows.clear()
		nextId = 1
	})

	it("keeps a valid offline_id and mints one otherwise", () => {
		expect(queuedOfflineId({ offline_id: "pos_offline_abc-123" })).toBe("pos_offline_abc-123")
		expect(queuedOfflineId({ offline_id: "nope" })).toMatch(/^pos_offline_/)
		expect(queuedOfflineId({ offline_id: "nope" })).not.toBe("nope")
		expect(queuedOfflineId({})).toMatch(/^pos_offline_/)
	})

	it("queues the sale under the cart's offline_id", async () => {
		const result = await saveOfflineInvoice(invoice({ offline_id: "pos_offline_cart-1" }))
		expect(result.offline_id).toBe("pos_offline_cart-1")
		expect(rows.size).toBe(1)
		expect([...rows.values()][0].data.offline_id).toBe("pos_offline_cart-1")
	})

	it("a second pay of the same cart returns the queued sale, not a second one", async () => {
		const first = await saveOfflineInvoice(invoice({ offline_id: "pos_offline_cart-1" }))
		const again = await saveOfflineInvoice(invoice({ offline_id: "pos_offline_cart-1" }))
		expect(rows.size).toBe(1)
		expect(again).toMatchObject({ success: true, id: first.id, offline_id: "pos_offline_cart-1", duplicate: true })
	})

	it("sales without an offline_id still get their own", async () => {
		const a = await saveOfflineInvoice(invoice())
		const b = await saveOfflineInvoice(invoice())
		expect(a.offline_id).not.toBe(b.offline_id)
		expect(rows.size).toBe(2)
	})
})
