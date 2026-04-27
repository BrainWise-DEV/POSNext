/**
 * Schema test: verify the new IndexedDB tables exist, accept rows, and
 * round-trip data. Catches schema regressions on the auto-versioning path.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { db } from "@/utils/offline/db"

const NEW_TABLES = [
	"taxes",
	"uoms",
	"item_groups",
	"brands",
	"loyalty_programs",
	"customer_queue",
]

describe("offline db schema", () => {
	beforeEach(async () => {
		// Ensure a clean slate between tests.
		await Promise.all(NEW_TABLES.map((name) => db.table(name).clear()))
	})

	afterEach(async () => {
		await Promise.all(NEW_TABLES.map((name) => db.table(name).clear()))
	})

	it("exposes the new offline cache tables", () => {
		const tableNames = db.tables.map((t) => t.name)
		for (const name of NEW_TABLES) {
			expect(tableNames).toContain(name)
		}
	})

	it("round-trips a tax template with its child rows", async () => {
		const tpl = {
			name: "TPL-VAT-15",
			title: "VAT 15%",
			company: "ACME",
			pos_profile: "PROFILE-A",
			disabled: 0,
			is_default: 1,
			taxes: [
				{
					account_head: "VAT - ACME",
					rate: 15,
					charge_type: "On Net Total",
					idx: 1,
				},
			],
		}
		await db.taxes.put(tpl)
		const fetched = await db.taxes.get("TPL-VAT-15")
		expect(fetched).toEqual(tpl)
	})

	it("filters taxes by pos_profile via index", async () => {
		await db.taxes.bulkPut([
			{ name: "T1", pos_profile: "A", company: "C1", taxes: [] },
			{ name: "T2", pos_profile: "B", company: "C1", taxes: [] },
			{ name: "T3", pos_profile: "A", company: "C2", taxes: [] },
		])
		const onlyA = await db.taxes.where("pos_profile").equals("A").toArray()
		expect(onlyA.map((t) => t.name).sort()).toEqual(["T1", "T3"])
	})

	it("stores customer queue rows with a unique offline_id", async () => {
		await db.customer_queue.add({
			offline_id: "off-1",
			data: { customer_name: "Walk-in 1" },
			timestamp: Date.now(),
			synced: false,
			retry_count: 0,
		})
		await expect(
			db.customer_queue.add({
				offline_id: "off-1", // duplicate — should violate unique constraint
				data: { customer_name: "Dup" },
				timestamp: Date.now(),
				synced: false,
				retry_count: 0,
			}),
		).rejects.toThrow()
	})

	it("auto-deletes a UOM when cleared", async () => {
		await db.uoms.bulkPut([{ name: "Nos" }, { name: "Box" }, { name: "Kg" }])
		expect(await db.uoms.count()).toBe(3)
		await db.uoms.clear()
		expect(await db.uoms.count()).toBe(0)
	})
})
