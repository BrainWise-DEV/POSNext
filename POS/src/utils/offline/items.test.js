import { beforeEach, describe, expect, it, vi } from "vitest";

const itemStore = new Map();

vi.mock("./db", () => {
	const items = {
		get: vi.fn(async (itemCode) => itemStore.get(itemCode) ?? undefined),
		update: vi.fn(async (itemCode, update) => {
			const existing = itemStore.get(itemCode);
			if (!existing) return 0;
			itemStore.set(itemCode, { ...existing, ...update });
			return 1;
		}),
		put: vi.fn(async (row) => {
			itemStore.set(row.item_code, { ...row });
			return row.item_code;
		}),
	};

	return {
		db: {
			items,
			transaction: vi.fn(async (_mode, _table, fn) => fn()),
		},
		getSetting: vi.fn(),
		setSetting: vi.fn(),
	};
});

const {
	parseSerialNumbers,
	persistItemBatchSerialData,
	consumeCachedSerials,
	returnCachedSerials,
	getCachedSerialData,
} = await import("./items");

describe("parseSerialNumbers", () => {
	it("parses newline-delimited strings", () => {
		expect(parseSerialNumbers("SN-1\nSN-2\n\n SN-3 ")).toEqual(["SN-1", "SN-2", "SN-3"]);
	});

	it("passes through arrays and empty input", () => {
		expect(parseSerialNumbers(["A", "B"])).toEqual(["A", "B"]);
		expect(parseSerialNumbers(null)).toEqual([]);
		expect(parseSerialNumbers("")).toEqual([]);
	});
});

describe("offline serial cache mutators", () => {
	beforeEach(() => {
		itemStore.clear();
		itemStore.set("ITEM-1", {
			item_code: "ITEM-1",
			item_name: "Widget",
			serial_no_data: [
				{ serial_no: "SN-1", warehouse: "Stores - T" },
				{ serial_no: "SN-2", warehouse: "Stores - T" },
				{ serial_no: "SN-3", warehouse: "Stores - T" },
			],
		});
	});

	it("consume then return restores serials (round-trip)", async () => {
		await consumeCachedSerials("ITEM-1", "SN-1\nSN-2");
		expect(await getCachedSerialData("ITEM-1")).toEqual([
			{ serial_no: "SN-3", warehouse: "Stores - T" },
		]);

		await returnCachedSerials("ITEM-1", ["SN-1", "SN-2"], "Stores - T");
		expect(await getCachedSerialData("ITEM-1")).toEqual([
			{ serial_no: "SN-1", warehouse: "Stores - T" },
			{ serial_no: "SN-2", warehouse: "Stores - T" },
			{ serial_no: "SN-3", warehouse: "Stores - T" },
		]);
	});

	it("does not create phantom rows when the item is missing", async () => {
		const ok = await persistItemBatchSerialData("MISSING", {
			serial_no_data: [{ serial_no: "SN-X", warehouse: "Stores - T" }],
		});
		expect(ok).toBe(false);
		expect(itemStore.has("MISSING")).toBe(false);
	});

	it("refuses to return serials without a warehouse when cache is empty", async () => {
		itemStore.set("ITEM-1", {
			item_code: "ITEM-1",
			item_name: "Widget",
			serial_no_data: [],
		});

		await returnCachedSerials("ITEM-1", ["SN-1"]);
		expect(await getCachedSerialData("ITEM-1")).toEqual([]);

		await returnCachedSerials("ITEM-1", ["SN-1"], "Stores - T");
		expect(await getCachedSerialData("ITEM-1")).toEqual([
			{ serial_no: "SN-1", warehouse: "Stores - T" },
		]);
	});
});
