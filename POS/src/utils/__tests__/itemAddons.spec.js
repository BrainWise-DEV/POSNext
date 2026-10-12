import { beforeEach, describe, expect, it, vi } from "vitest";

const catalogData = { value: null };
vi.mock("@/utils/apiWrapper", () => ({ call: vi.fn(async () => catalogData.value) }));
vi.mock("@/utils/offline/db", () => ({ getSetting: vi.fn(), setSetting: vi.fn() }));

import {
	addonKey,
	getAvailableAddons,
	hasAvailableAddons,
	refreshAddonCatalog,
} from "@/utils/itemAddons";

// Shaped like nextend.item_addon.get_addon_catalog.
const CATALOG = {
	carrier_item: "ADDON-TINTING",
	rules: [
		{
			bases: { Item: [], Brand: ["Propan Base"], "Item Group": [] },
			addons: ["PRP-YEL", "PRP-RED", "AVN-BLK"],
			groups: ["Tinta Propan", "Tinta Avian"],
		},
		{
			bases: { Item: ["OTHER-BASE"], Brand: [], "Item Group": [] },
			addons: ["AVN-BLK"],
			groups: [],
		},
	],
	overrides: { "BASE-X": { add: ["LOOSE"], exclude: ["PRP-RED"] } },
	groups: {
		"Tinta Propan": ["PRP-YEL", "PRP-RED"],
		"Tinta Avian": ["AVN-BLK", "AVN-WHT"],
	},
	item_names: { "PRP-YEL": "Propan Yellow", "PRP-RED": "Propan Red", "AVN-BLK": "Avian Black" },
	bins: {
		"PRP-YEL": ["W1"],
		"PRP-RED": ["W1", "W2"],
		"AVN-BLK": ["W1"],
		"AVN-WHT": ["W3"],
		LOOSE: ["W1"],
	},
};

const base = (extra = {}) => ({
	item_code: "BASE-X",
	brand: "Propan Base",
	item_group: "Base",
	warehouse: "W1",
	...extra,
});

async function loadCatalog(data) {
	catalogData.value = data;
	await refreshAddonCatalog();
}

describe("getAvailableAddons", () => {
	beforeEach(async () => {
		await loadCatalog(CATALOG);
	});

	it("offers matching groups and per item tinta with their group", () => {
		expect(getAvailableAddons(base({ item_code: "BASE-Y" }))).toEqual({
			items: [
				{ item_code: "AVN-BLK", item_name: "Avian Black", addon_group: "Tinta Avian" },
				{ item_code: "PRP-RED", item_name: "Propan Red", addon_group: "Tinta Propan" },
				{ item_code: "PRP-YEL", item_name: "Propan Yellow", addon_group: "Tinta Propan" },
			],
			groups: ["Tinta Avian", "Tinta Propan"],
		});
	});

	it("applies the base overrides to per item tinta, never to groups", () => {
		const { items, groups } = getAvailableAddons(base());
		expect(items.map((i) => i.item_code)).toEqual(["AVN-BLK", "LOOSE", "PRP-YEL"]);
		expect(items.find((i) => i.item_code === "LOOSE").addon_group).toBeNull();
		expect(groups).toEqual(["Tinta Avian", "Tinta Propan"]);
	});

	it("keeps a group only while one of its members is in the warehouse", () => {
		// W2 holds Propan Red only; Avian has nothing there.
		expect(getAvailableAddons(base({ item_code: "BASE-Y", warehouse: "W2" }))).toEqual({
			items: [{ item_code: "PRP-RED", item_name: "Propan Red", addon_group: "Tinta Propan" }],
			groups: ["Tinta Propan"],
		});
		// W3 holds an Avian member that is not offered per item - the group still is.
		expect(getAvailableAddons(base({ item_code: "BASE-Y", warehouse: "W3" }))).toEqual({
			items: [],
			groups: ["Tinta Avian"],
		});
	});

	it("offers nothing to unmatched or free items", () => {
		expect(hasAvailableAddons(base({ item_code: "Z", brand: "Other" }))).toBe(false);
		expect(hasAvailableAddons(base({ is_free_item: 1 }))).toBe(false);
		expect(hasAvailableAddons(base())).toBe(true);
	});

	it("still reads a catalog cached before groups existed", async () => {
		const { groups: _groups, ...old } = CATALOG;
		await loadCatalog({ ...old, rules: old.rules.map(({ groups: _g, ...rule }) => rule) });
		const result = getAvailableAddons(base({ item_code: "BASE-Y" }));
		expect(result.groups).toEqual([]);
		expect(result.items.map((i) => [i.item_code, i.addon_group])).toEqual([
			["AVN-BLK", null],
			["PRP-RED", null],
			["PRP-YEL", null],
		]);
	});
});

describe("addonKey", () => {
	it("tells a tinta apart from a gelondongan group", () => {
		expect(addonKey({ item_code: "PRP-YEL", addon_group: "Tinta Propan" })).toBe("PRP-YEL");
		expect(addonKey({ item_code: null, addon_group: "Tinta Propan" })).toBe("group:Tinta Propan");
	});
});
