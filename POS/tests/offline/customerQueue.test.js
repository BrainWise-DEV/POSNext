/**
 * Tests the offline customer creation queue end-to-end (with fake
 * IndexedDB) and the replay path (with `call` mocked).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// `call` lives in @/utils/apiWrapper — mock it before importing customerQueue.
vi.mock("@/utils/apiWrapper", () => ({
	call: vi.fn(),
}))

import { call } from "@/utils/apiWrapper"
import { db } from "@/utils/offline/db"
import {
	enqueueOfflineCustomer,
	getQueuedOfflineCustomers,
	syncOfflineCustomers,
} from "@/utils/offline/customerQueue"

describe("customer queue", () => {
	beforeEach(async () => {
		await db.customer_queue.clear()
		await db.customers.clear()
		call.mockReset()
	})

	afterEach(async () => {
		await db.customer_queue.clear()
		await db.customers.clear()
	})

	it("enqueues with a placeholder customer record visible to the UI", async () => {
		const { offline_id, placeholder_name } = await enqueueOfflineCustomer({
			customer_name: "Walk-in Alpha",
			mobile_no: "+15550100",
		})

		expect(offline_id).toMatch(/^pos_offline_/)
		expect(placeholder_name).toMatch(/^OFFLINE-/)

		const queue = await getQueuedOfflineCustomers()
		expect(queue).toHaveLength(1)
		expect(queue[0].synced).toBe(false)
		expect(queue[0].data.customer_name).toBe("Walk-in Alpha")

		const placeholder = await db.customers.get(placeholder_name)
		expect(placeholder).toMatchObject({
			customer_name: "Walk-in Alpha",
			mobile_no: "+15550100",
			pending_offline_id: offline_id,
			placeholder: true,
		})
	})

	it("rejects when customer_name is missing", async () => {
		await expect(enqueueOfflineCustomer({})).rejects.toThrow(/customer_name/i)
	})

	it("replays queued customers, replaces placeholder with real record", async () => {
		const { offline_id, placeholder_name } = await enqueueOfflineCustomer({
			customer_name: "Beta Customer",
			mobile_no: "+15550101",
		})

		call.mockResolvedValueOnce({
			message: {
				name: "CUST-BETA-0001",
				deduplicated: false,
				doc: {
					name: "CUST-BETA-0001",
					customer_name: "Beta Customer",
					mobile_no: "+15550101",
				},
			},
		})

		const result = await syncOfflineCustomers()
		expect(result).toEqual({ success: 1, failed: 0, deduplicated: 0 })

		// Placeholder gone, real record present.
		expect(await db.customers.get(placeholder_name)).toBeUndefined()
		const real = await db.customers.get("CUST-BETA-0001")
		expect(real?.customer_name).toBe("Beta Customer")

		// Queue drained.
		const remaining = await getQueuedOfflineCustomers()
		expect(remaining).toHaveLength(0)

		expect(call).toHaveBeenCalledWith(
			"pos_next.api.customers.replay_offline_customer",
			expect.objectContaining({
				offline_id,
				customer_name: "Beta Customer",
				mobile_no: "+15550101",
			}),
		)
	})

	it("counts a deduplicated replay separately from new creates", async () => {
		await enqueueOfflineCustomer({ customer_name: "Gamma" })
		call.mockResolvedValueOnce({
			message: {
				name: "CUST-GAMMA",
				deduplicated: true,
				doc: { name: "CUST-GAMMA", customer_name: "Gamma" },
			},
		})

		const result = await syncOfflineCustomers()
		expect(result.success).toBe(0)
		expect(result.deduplicated).toBe(1)
		expect(result.failed).toBe(0)
	})

	it("bumps retry_count and keeps queue row when replay fails", async () => {
		await enqueueOfflineCustomer({ customer_name: "Delta" })
		call.mockRejectedValueOnce(new Error("network down"))

		const result = await syncOfflineCustomers()
		expect(result.failed).toBe(1)
		expect(result.success).toBe(0)

		const queue = await getQueuedOfflineCustomers()
		expect(queue).toHaveLength(1)
		expect(queue[0].retry_count).toBe(1)
		expect(queue[0].last_error).toContain("network down")
	})
})
