/**
 * Tests for utils/offline/diskBackup.js — the QZ-Tray-backed on-disk
 * mirror for offline queues. We mock the qz-tray module + the qzTray
 * wrapper so the tests run without a live QZ helper.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// vi.mock factories are hoisted above ESM imports, so any state they
// touch must come via vi.hoisted (which is hoisted with them). Vitest
// exposes `vi` as a global when test.globals is true, which lets us
// build the mocks inside hoisted without needing a require().
const { qzMock, connectMock, qzConnectedHolder } = vi.hoisted(() => ({
	qzMock: {
		file: {
			write: vi.fn(),
			read: vi.fn(),
			list: vi.fn(),
			remove: vi.fn(),
		},
	},
	connectMock: vi.fn(),
	// Plain object with a `value` property mimics a Vue ref so the
	// production code's `qzConnected.value` access keeps working.
	qzConnectedHolder: { value: true },
}))

vi.mock("qz-tray", () => ({
	default: qzMock,
}))

vi.mock("@/utils/qzTray", () => ({
	connect: (...args) => connectMock(...args),
	qzConnected: qzConnectedHolder,
}))

const qzConnectedRef = qzConnectedHolder

import { db } from "@/utils/offline/db"
import {
	backfillMirrorFromIndexedDB,
	disableDiskMirror,
	enableDiskMirror,
	isMirrorAvailable,
	mirrorOfflineCustomer,
	mirrorOfflineInvoice,
	removeMirroredCustomer,
	removeMirroredInvoice,
	restoreFromDisk,
} from "@/utils/offline/diskBackup"

const reset = () => {
	qzMock.file.write.mockReset()
	qzMock.file.read.mockReset()
	qzMock.file.list.mockReset()
	qzMock.file.remove.mockReset()
	connectMock.mockReset()
	qzConnectedRef.value = true
	enableDiskMirror()
}

describe("offline/diskBackup", () => {
	beforeEach(async () => {
		reset()
		await Promise.all([db.invoice_queue.clear(), db.customer_queue.clear()])
	})

	afterEach(async () => {
		reset()
		await Promise.all([db.invoice_queue.clear(), db.customer_queue.clear()])
	})

	it("isMirrorAvailable reflects QZ connection + enable flag", () => {
		expect(isMirrorAvailable()).toBe(true)
		qzConnectedRef.value = false
		expect(isMirrorAvailable()).toBe(false)
		qzConnectedRef.value = true
		disableDiskMirror()
		expect(isMirrorAvailable()).toBe(false)
		enableDiskMirror()
		expect(isMirrorAvailable()).toBe(true)
	})

	it("writes invoice rows to a sandboxed file path", async () => {
		qzMock.file.write.mockResolvedValue(undefined)
		const row = {
			offline_id: "pos_offline_inv_1",
			data: { customer: "Walk-in", items: [{ item_code: "A" }] },
			timestamp: 1700000000000,
			retry_count: 0,
			stock_delta: [{ item_code: "A", warehouse: "W", qty: 1 }],
		}

		const result = await mirrorOfflineInvoice(row)
		expect(result).toEqual({ mirrored: true })
		expect(qzMock.file.write).toHaveBeenCalledOnce()
		const [path, opts] = qzMock.file.write.mock.calls[0]
		expect(path).toBe("pos_next/invoices/pos_offline_inv_1.json")
		expect(opts.sandbox).toBe(true)
		const payload = JSON.parse(opts.data)
		expect(payload.kind).toBe("invoice")
		expect(payload.row.offline_id).toBe("pos_offline_inv_1")
		expect(payload.row.data.customer).toBe("Walk-in")
	})

	it("returns mirrored:false when QZ is unavailable, never throws", async () => {
		qzConnectedRef.value = false
		connectMock.mockResolvedValue(false)

		const result = await mirrorOfflineInvoice({
			offline_id: "x",
			data: {},
			timestamp: 1,
		})
		expect(result.mirrored).toBe(false)
		expect(result.reason).toBe("qz_unavailable")
		expect(qzMock.file.write).not.toHaveBeenCalled()
	})

	it("returns mirrored:false on QZ write failure but does not throw", async () => {
		qzMock.file.write.mockRejectedValue(new Error("disk full"))
		const result = await mirrorOfflineInvoice({
			offline_id: "y",
			data: {},
			timestamp: 1,
		})
		expect(result.mirrored).toBe(false)
		expect(result.reason).toBe("qz_error")
	})

	it("sanitizes offline_id for filesystem safety", async () => {
		qzMock.file.write.mockResolvedValue(undefined)
		await mirrorOfflineInvoice({
			offline_id: "../../etc/passwd",
			data: {},
			timestamp: 1,
		})
		const [path] = qzMock.file.write.mock.calls[0]
		expect(path).not.toContain("..")
		expect(path).not.toContain("/etc/")
		expect(path).toMatch(/^pos_next\/invoices\/[a-zA-Z0-9._-]+\.json$/)
	})

	it("removeMirroredInvoice calls qz.file.remove (and ignores failures)", async () => {
		qzMock.file.remove.mockResolvedValue(undefined)
		await removeMirroredInvoice("xyz")
		expect(qzMock.file.remove).toHaveBeenCalledWith(
			"pos_next/invoices/xyz.json",
			{ sandbox: true },
		)

		// Failure shouldn't throw.
		qzMock.file.remove.mockRejectedValue(new Error("not found"))
		await expect(removeMirroredInvoice("missing")).resolves.toBeUndefined()
	})

	it("mirrorOfflineCustomer + removeMirroredCustomer hit the customer dir", async () => {
		qzMock.file.write.mockResolvedValue(undefined)
		await mirrorOfflineCustomer({
			offline_id: "c1",
			data: { customer_name: "Alice" },
			timestamp: 1,
		})
		expect(qzMock.file.write).toHaveBeenCalledWith(
			"pos_next/customers/c1.json",
			expect.objectContaining({ sandbox: true }),
		)

		qzMock.file.remove.mockResolvedValue(undefined)
		await removeMirroredCustomer("c1")
		expect(qzMock.file.remove).toHaveBeenCalledWith(
			"pos_next/customers/c1.json",
			{ sandbox: true },
		)
	})

	it("restoreFromDisk re-inserts missing rows but skips existing ones", async () => {
		// Two invoices on disk: inv-a (already in DB), inv-b (new).
		qzMock.file.list.mockImplementation((dir) => {
			if (dir === "pos_next/invoices")
				return Promise.resolve(["inv-a.json", "inv-b.json"])
			if (dir === "pos_next/customers") return Promise.resolve(["cust-x.json"])
			return Promise.resolve([])
		})

		qzMock.file.read.mockImplementation((path) => {
			if (path === "pos_next/invoices/inv-a.json") {
				return Promise.resolve(
					JSON.stringify({
						kind: "invoice",
						row: {
							offline_id: "inv-a",
							timestamp: 1,
							data: { customer: "A", items: [{ item_code: "a" }] },
						},
					}),
				)
			}
			if (path === "pos_next/invoices/inv-b.json") {
				return Promise.resolve(
					JSON.stringify({
						kind: "invoice",
						row: {
							offline_id: "inv-b",
							timestamp: 2,
							retry_count: 0,
							stock_delta: [],
							data: { customer: "B", items: [{ item_code: "b" }] },
						},
					}),
				)
			}
			if (path === "pos_next/customers/cust-x.json") {
				return Promise.resolve(
					JSON.stringify({
						kind: "customer",
						row: {
							offline_id: "cust-x",
							timestamp: 3,
							data: { customer_name: "Mr X", mobile_no: "+1" },
						},
					}),
				)
			}
			return Promise.resolve(null)
		})

		// Pre-seed inv-a so restore should skip it.
		await db.invoice_queue.add({
			offline_id: "inv-a",
			data: { customer: "A" },
			timestamp: 1,
			synced: false,
			retry_count: 0,
		})

		const result = await restoreFromDisk()

		expect(result.ran).toBe(true)
		expect(result.invoicesRestored).toBe(1)
		expect(result.invoicesSkipped).toBe(1)
		expect(result.customersRestored).toBe(1)

		const restoredInvoice = await db.invoice_queue
			.where("offline_id")
			.equals("inv-b")
			.first()
		expect(restoredInvoice?.data?.customer).toBe("B")
		expect(restoredInvoice?.restored_from_disk_at).toBeTruthy()

		const restoredCustomer = await db.customer_queue
			.where("offline_id")
			.equals("cust-x")
			.first()
		expect(restoredCustomer?.data?.customer_name).toBe("Mr X")
	})

	it("restoreFromDisk reports ran:false when QZ is unavailable", async () => {
		qzConnectedRef.value = false
		connectMock.mockResolvedValue(false)
		const result = await restoreFromDisk()
		expect(result).toMatchObject({
			ran: false,
			invoicesRestored: 0,
			customersRestored: 0,
		})
		expect(qzMock.file.list).not.toHaveBeenCalled()
	})

	it("backfillMirrorFromIndexedDB writes every pending row", async () => {
		qzMock.file.write.mockResolvedValue(undefined)
		await db.invoice_queue.bulkAdd([
			{
				offline_id: "p1",
				data: { customer: "A" },
				timestamp: 1,
				synced: false,
				retry_count: 0,
			},
			{
				offline_id: "p2",
				data: { customer: "B" },
				timestamp: 2,
				synced: true, // already synced — should be skipped
				retry_count: 0,
			},
		])
		await db.customer_queue.add({
			offline_id: "qc1",
			data: { customer_name: "Q" },
			timestamp: 1,
			synced: false,
			retry_count: 0,
		})

		const counts = await backfillMirrorFromIndexedDB()
		expect(counts.invoices).toBe(1)
		expect(counts.customers).toBe(1)
		expect(qzMock.file.write).toHaveBeenCalledTimes(2)
	})
})
