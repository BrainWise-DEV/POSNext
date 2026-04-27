/**
 * Tests for the new offline reference-data cache wrappers in
 * `utils/offline/cache.js` (taxes, UOMs, loyalty programs, item groups,
 * brands, and the bundle endpoint with fallback). All `call()` traffic
 * is mocked.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/utils/apiWrapper", () => ({
	call: vi.fn(),
}))

import { call } from "@/utils/apiWrapper"
import { db } from "@/utils/offline/db"
import {
	cacheBrandsFromServer,
	cacheCustomersFromServer,
	cacheItemGroupsFromServer,
	cacheLoyaltyProgramsFromServer,
	cacheOfflineBundleFromServer,
	cacheTaxesFromServer,
	cacheUomsFromServer,
	getCachedBrands,
	getCachedItemGroups,
	getCachedLoyaltyPrograms,
	getCachedTaxes,
	getCachedUoms,
} from "@/utils/offline/cache"

const PROFILE = "PROFILE-X"

describe("offline reference-data cache", () => {
	beforeEach(async () => {
		await Promise.all([
			db.taxes.clear(),
			db.uoms.clear(),
			db.item_groups.clear(),
			db.brands.clear(),
			db.loyalty_programs.clear(),
			db.customers.clear(),
		])
		call.mockReset()
	})

	afterEach(async () => {
		await Promise.all([
			db.taxes.clear(),
			db.uoms.clear(),
			db.item_groups.clear(),
			db.brands.clear(),
			db.loyalty_programs.clear(),
			db.customers.clear(),
		])
	})

	it("caches taxes tagged with the pos_profile", async () => {
		call.mockResolvedValueOnce({
			message: [
				{ name: "T1", title: "VAT 15%", company: "C", taxes: [] },
				{ name: "T2", title: "VAT 5%", company: "C", taxes: [] },
			],
		})
		const result = await cacheTaxesFromServer(PROFILE)
		expect(result.taxes).toHaveLength(2)

		const cached = await getCachedTaxes(PROFILE)
		expect(cached).toHaveLength(2)
		for (const row of cached) {
			expect(row.pos_profile).toBe(PROFILE)
		}
	})

	it("caches UOMs and reads them back", async () => {
		call.mockResolvedValueOnce({
			message: [{ name: "Nos" }, { name: "Box" }, { name: "Kg" }],
		})
		await cacheUomsFromServer()
		const uoms = await getCachedUoms()
		expect(uoms.map((u) => u.name).sort()).toEqual(["Box", "Kg", "Nos"])
	})

	it("caches loyalty programs", async () => {
		call.mockResolvedValueOnce({
			message: [
				{ name: "LP1", loyalty_program_name: "Gold", collection_rules: [] },
			],
		})
		await cacheLoyaltyProgramsFromServer({ company: "ACME" })
		const programs = await getCachedLoyaltyPrograms()
		expect(programs).toHaveLength(1)
		expect(programs[0].name).toBe("LP1")
	})

	it("caches item groups and brands", async () => {
		call
			.mockResolvedValueOnce({
				message: [
					{ name: "Food", parent_item_group: "All Item Groups", is_group: 0 },
				],
			})
			.mockResolvedValueOnce({
				message: [{ name: "Acme" }, { name: "Globex" }],
			})

		await cacheItemGroupsFromServer(PROFILE)
		await cacheBrandsFromServer(PROFILE)

		expect((await getCachedItemGroups()).map((g) => g.name)).toEqual(["Food"])
		expect((await getCachedBrands()).map((b) => b.name).sort()).toEqual([
			"Acme",
			"Globex",
		])
	})

	it("uses bundle endpoint when available", async () => {
		call.mockResolvedValueOnce({
			message: {
				taxes: [{ name: "T1", title: "VAT", company: "C", taxes: [] }],
				uoms: [{ name: "Nos" }],
				loyalty_programs: [
					{ name: "LP1", loyalty_program_name: "Gold", collection_rules: [] },
				],
			},
		})

		const bundle = await cacheOfflineBundleFromServer(PROFILE, { company: "C" })
		expect(bundle.taxes).toHaveLength(1)
		expect(bundle.uoms).toHaveLength(1)
		expect(bundle.loyalty_programs).toHaveLength(1)

		// Should have only made the single bundle call.
		expect(call).toHaveBeenCalledTimes(1)
		expect(call.mock.calls[0][0]).toBe(
			"pos_next.api.offline_data.get_offline_bundle",
		)

		// And data should be persisted.
		expect(await getCachedTaxes(PROFILE)).toHaveLength(1)
		expect(await getCachedUoms()).toHaveLength(1)
		expect(await getCachedLoyaltyPrograms()).toHaveLength(1)
	})

	it("falls back to per-endpoint calls when the bundle endpoint is missing", async () => {
		// Bundle call → fail
		call.mockRejectedValueOnce(new Error("AttributeError: no method"))
		// Then the three per-endpoint calls succeed
		call
			.mockResolvedValueOnce({ message: [{ name: "T2", taxes: [] }] }) // taxes
			.mockResolvedValueOnce({ message: [{ name: "Box" }] }) // uoms
			.mockResolvedValueOnce({
				message: [{ name: "LP2", collection_rules: [] }],
			}) // loyalty

		const bundle = await cacheOfflineBundleFromServer(PROFILE)
		expect(bundle.taxes).toHaveLength(1)
		expect(bundle.uoms).toHaveLength(1)
		expect(bundle.loyalty_programs).toHaveLength(1)
		expect(call).toHaveBeenCalledTimes(4)
	})

	it("falls back to legacy customers endpoint when the offline endpoint is missing", async () => {
		// First call (enriched) — fail
		call.mockRejectedValueOnce(new Error("Not whitelisted"))
		// Second call (legacy) — succeed
		call.mockResolvedValueOnce({
			message: [
				{ name: "C1", customer_name: "Alice" },
				{ name: "C2", customer_name: "Bob" },
			],
		})

		const result = await cacheCustomersFromServer(PROFILE)
		expect(result.customers).toHaveLength(2)
		expect(call).toHaveBeenCalledTimes(2)
		expect(call.mock.calls[0][0]).toBe(
			"pos_next.api.customers.get_customers_for_offline",
		)
		expect(call.mock.calls[1][0]).toBe("pos_next.api.customers.get_customers")
	})
})
