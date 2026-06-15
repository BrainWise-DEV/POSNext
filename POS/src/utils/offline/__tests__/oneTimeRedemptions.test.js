// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

// In-memory stand-in for the Dexie `one_time_redemptions` table, keyed by customer.
const store = new Map();

const fakeTable = {
	async get(customer) {
		const row = store.get(customer);
		return row ? JSON.parse(JSON.stringify(row)) : undefined;
	},
	async put(row) {
		store.set(row.customer, JSON.parse(JSON.stringify(row)));
	},
	async toArray() {
		return Array.from(store.values()).map((r) => JSON.parse(JSON.stringify(r)));
	},
};

// Mock Dexie so importing db.js doesn't touch IndexedDB. The constructed instance
// exposes our fake `one_time_redemptions` table and no-op schema methods.
vi.mock("dexie", () => {
	class FakeDexie {
		constructor() {
			this.one_time_redemptions = fakeTable;
		}
		version() {
			return { stores: () => {} };
		}
		on() {}
	}
	return { default: FakeDexie };
});

vi.mock("@/utils/logger", () => {
	const noop = { error: () => {}, warn: () => {}, info: () => {}, debug: () => {}, success: () => {} };
	return { logger: { ...noop, create: () => noop } };
});

const {
	getOneTimeRedemptions,
	setOneTimeRedemptions,
	addOfflineRedemptions,
	releaseOfflineRedemptions,
} = await import("../db");

beforeEach(() => {
	store.clear();
});

describe("one-time redemption cache (offline/online)", () => {
	it("P0: offline redemption is recorded and visible to the gate", async () => {
		await addOfflineRedemptions("CUST-1", ["RULE-A"], "off-1");
		expect(await getOneTimeRedemptions("CUST-1")).toEqual(["RULE-A"]);
	});

	it("effective set is the union of server + offline buckets", async () => {
		await setOneTimeRedemptions("CUST-1", ["RULE-S"]);
		await addOfflineRedemptions("CUST-1", ["RULE-A"], "off-1");
		expect((await getOneTimeRedemptions("CUST-1")).sort()).toEqual(["RULE-A", "RULE-S"]);
	});

	it("P3: online fetch REPLACES server set (release self-heals) but keeps offline redemptions", async () => {
		await setOneTimeRedemptions("CUST-1", ["RULE-S1", "RULE-S2"]);
		await addOfflineRedemptions("CUST-1", ["RULE-OFF"], "off-1");
		const eff = await setOneTimeRedemptions("CUST-1", ["RULE-S1"]);
		expect(eff.sort()).toEqual(["RULE-OFF", "RULE-S1"]); // S2 released, offline kept
	});

	it("P2: voiding one offline invoice releases only its own redemptions", async () => {
		await addOfflineRedemptions("CUST-1", ["RULE-A"], "off-1");
		await addOfflineRedemptions("CUST-1", ["RULE-A"], "off-2");
		await releaseOfflineRedemptions("off-1", "CUST-1");
		expect(await getOneTimeRedemptions("CUST-1")).toEqual(["RULE-A"]); // off-2 still blocks
		await releaseOfflineRedemptions("off-2", "CUST-1");
		expect(await getOneTimeRedemptions("CUST-1")).toEqual([]);
	});

	it("release returns the effective set when the customer is known (no re-read needed)", async () => {
		await setOneTimeRedemptions("CUST-1", ["RULE-S"]);
		await addOfflineRedemptions("CUST-1", ["RULE-OFF"], "off-1");
		const eff = await releaseOfflineRedemptions("off-1", "CUST-1");
		expect(eff).toEqual(["RULE-S"]); // offline bucket dropped, server set remains
	});

	it("P2: release works without knowing the customer (scans all rows)", async () => {
		await addOfflineRedemptions("CUST-1", ["RULE-A"], "off-1");
		await addOfflineRedemptions("CUST-2", ["RULE-B"], "off-2");
		await releaseOfflineRedemptions("off-1");
		expect(await getOneTimeRedemptions("CUST-1")).toEqual([]);
		expect(await getOneTimeRedemptions("CUST-2")).toEqual(["RULE-B"]);
	});

	it("backward compat: a legacy flat `rules` row is read as serverRules", async () => {
		store.set("CUST-1", { customer: "CUST-1", rules: ["LEGACY-RULE"] });
		expect(await getOneTimeRedemptions("CUST-1")).toEqual(["LEGACY-RULE"]);
		await addOfflineRedemptions("CUST-1", ["NEW-RULE"], "off-1");
		expect((await getOneTimeRedemptions("CUST-1")).sort()).toEqual(["LEGACY-RULE", "NEW-RULE"]);
	});
});
