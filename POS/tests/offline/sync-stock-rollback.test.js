/**
 * Tests for the new "stock rollback on sync failure" path in
 * `utils/offline/sync.js`. Verifies that:
 *   - `saveOfflineInvoice` records `stock_delta` and applies it
 *   - manually deleting an unsynced invoice re-credits the stock
 *   - hitting the retry ceiling reverts the stock automatically
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/utils/apiWrapper", () => ({
	call: vi.fn().mockRejectedValue(new Error("network down")),
}))

import { db } from "@/utils/offline/db"
import {
	deleteOfflineInvoice,
	getLocalStock,
	saveOfflineInvoice,
	syncOfflineInvoices,
} from "@/utils/offline/sync"

const ITEM = "ITEM-A"
const WAREHOUSE = "WH-Main"

const baseInvoice = (qty) => ({
	customer: "Walk-in",
	posting_date: "2026-04-26",
	items: [
		{
			item_code: ITEM,
			warehouse: WAREHOUSE,
			quantity: qty,
			rate: 100,
		},
	],
})

describe("sync — optimistic stock + rollback", () => {
	beforeEach(async () => {
		await db.invoice_queue.clear()
		await db.stock.clear()
		await db.stock.put({
			item_code: ITEM,
			warehouse: WAREHOUSE,
			qty: 10,
			updated_at: Date.now(),
		})
	})

	afterEach(async () => {
		await db.invoice_queue.clear()
		await db.stock.clear()
	})

	it("records stock_delta on saveOfflineInvoice and decrements stock", async () => {
		const result = await saveOfflineInvoice(baseInvoice(3))
		expect(result.success).toBe(true)

		const queueRow = await db.invoice_queue.get(result.id)
		expect(queueRow.stock_delta).toEqual([
			{ item_code: ITEM, warehouse: WAREHOUSE, qty: 3 },
		])
		expect(queueRow.stock_reverted).toBe(false)

		expect(await getLocalStock(ITEM, WAREHOUSE)).toBe(7)
	})

	it("reverts stock when an unsynced offline invoice is deleted", async () => {
		const result = await saveOfflineInvoice(baseInvoice(4))
		expect(await getLocalStock(ITEM, WAREHOUSE)).toBe(6)

		await deleteOfflineInvoice(result.id)
		expect(await getLocalStock(ITEM, WAREHOUSE)).toBe(10)
		expect(await db.invoice_queue.get(result.id)).toBeUndefined()
	})

	it("reverts stock when retry ceiling is hit during sync", async () => {
		// Save and depress stock to 8.
		const { id, offline_id } = await saveOfflineInvoice(baseInvoice(2))
		expect(await getLocalStock(ITEM, WAREHOUSE)).toBe(8)

		// Skip the dedup-check round-trip — pre-mark it not synced.
		const apiMock = (await import("@/utils/apiWrapper")).call
		// Both check_offline_invoice_synced and submit_invoice will reject
		// thanks to the default mock implementation. We just need to drive
		// the queue through MAX_RETRY_COUNT iterations.
		apiMock.mockResolvedValue({ synced: false })
		// Make submit_invoice fail. We can rely on the overall mock below.

		// Drive sync 5 times so retry_count reaches MAX (default 5).
		for (let i = 0; i < 6; i += 1) {
			apiMock.mockResolvedValueOnce({ synced: false }) // dedup check
			apiMock.mockRejectedValueOnce(new Error(`network down ${i}`)) // submit
			await syncOfflineInvoices().catch(() => {})
		}

		const finalRow = await db.invoice_queue.get(id)
		// Once retry_count >= 5 the sync code marks failure and reverts stock.
		expect(finalRow.sync_failed).toBe(true)
		expect(finalRow.stock_reverted).toBe(true)
		expect(await getLocalStock(ITEM, WAREHOUSE)).toBe(10)
		expect(offline_id).toMatch(/^pos_offline_/)
	}, 15_000)
})
