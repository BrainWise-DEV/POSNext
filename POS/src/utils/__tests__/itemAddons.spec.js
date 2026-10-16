import { beforeEach, describe, expect, it, vi } from "vitest";

const catalogData = { value: null };
vi.mock("@/utils/apiWrapper", () => ({ call: vi.fn(async () => catalogData.value) }));
vi.mock("@/utils/offline/db", () => ({ getSetting: vi.fn(), setSetting: vi.fn() }));

import {
	JENIS_JUAL,
	getAvailableAddons,
	hasAvailableAddons,
	isOpenPriceItem,
	isTintable,
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
		{
			jenis: "Add On Jual",
			bases: { Item: [], Brand: ["Propan Base"], "Item Group": [] },
			addons: ["JASA-ANTAR"],
			groups: [],
		},
	],
	overrides: { "BASE-X": { add: ["LOOSE", "JASA-POTONG"], exclude: ["PRP-RED", "JASA-ANTAR"] } },
	service_items: ["JASA-ANTAR", "JASA-POTONG"],
	groups: {
		"Tinta Propan": ["PRP-YEL", "PRP-RED"],
		"Tinta Avian": ["AVN-BLK", "AVN-WHT"],
	},
	item_names: { "PRP-YEL": "Propan Yellow", "PRP-RED": "Propan Red", "AVN-BLK": "Avian Black" },
	item_brands: {
		"PRP-YEL": "Propan Base",
		"PRP-RED": "Propan Base",
		"AVN-BLK": "Avian",
		"AVN-WHT": "Avian",
	},
	open_price_items: ["BASE-X"],
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
		expect(getAvailableAddons(base({ item_code: "Z", brand: "Other" })).items).toEqual([]);
		expect(getAvailableAddons(base({ is_free_item: 1 })).items).toEqual([]);
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

describe("Add On Jual", () => {
	beforeEach(async () => {
		await loadCatalog(CATALOG);
	});

	it("offers services of jual rules only, whatever the warehouse", () => {
		expect(getAvailableAddons(base({ item_code: "BASE-Y", warehouse: "W9" }), JENIS_JUAL)).toEqual({
			items: [{ item_code: "JASA-ANTAR", item_name: "JASA-ANTAR", addon_group: null }],
			groups: [],
		});
		expect(hasAvailableAddons(base({ item_code: "OTHER-BASE", brand: null, item_group: "x" }))).toBe(
			false
		);
	});

	it("applies overrides to the kind of their item", () => {
		// BASE-X adds JASA-POTONG and drops JASA-ANTAR; its tinta overrides stay on the tinta side
		expect(getAvailableAddons(base(), JENIS_JUAL).items.map((i) => i.item_code)).toEqual([
			"JASA-POTONG",
		]);
		expect(getAvailableAddons(base()).items.map((i) => i.item_code)).toEqual([
			"AVN-BLK",
			"LOOSE",
			"PRP-YEL",
		]);
	});

	it("treats rules of a catalog cached before jenis existed as tinta", () => {
		expect(getAvailableAddons(base({ item_code: "BASE-Y" })).items).toHaveLength(3);
	});
});

describe("isTintable", () => {
	beforeEach(async () => {
		await loadCatalog(CATALOG);
	});

	it("needs the offered tinta in the warehouse to share one brand", () => {
		// OTHER-BASE is offered Avian Black only; the base's own brand plays no part
		expect(isTintable(base({ item_code: "OTHER-BASE", brand: "X", item_group: "x" }))).toBe(true);
		expect(isTintable(base({ item_code: "OTHER-BASE", brand: null, item_group: "x" }))).toBe(true);
		// BASE-X: Propan Yellow + Avian Black + LOOSE in W1 - two brands, ambiguous
		expect(isTintable(base())).toBe(false);
	});

	it("counts members of an offered group that are in the warehouse", () => {
		// W2: Propan Red per item; W3: only AVN-WHT through the Avian group
		expect(isTintable(base({ item_code: "BASE-Y", warehouse: "W2" }))).toBe(true);
		expect(isTintable(base({ item_code: "BASE-Y", warehouse: "W3" }))).toBe(true);
		expect(isTintable(base({ item_code: "BASE-Y", warehouse: "W9" }))).toBe(false);
	});

	it("is false without a rule or a catalog", async () => {
		expect(isTintable(base({ item_code: "Z", brand: "Other" }))).toBe(false);
		await loadCatalog(null);
		expect(isTintable(base({ item_code: "OTHER-BASE", item_group: "x" }))).toBe(false);
	});
});

describe("isOpenPriceItem", () => {
	it("follows the catalog list", async () => {
		await loadCatalog(CATALOG);
		expect(isOpenPriceItem("BASE-X")).toBe(true);
		expect(isOpenPriceItem("BASE-Y")).toBe(false);
		expect(isOpenPriceItem(null)).toBe(false);
	});

	it("is false for a catalog cached before the list existed", async () => {
		const { open_price_items: _o, ...old } = CATALOG;
		await loadCatalog(old);
		expect(isOpenPriceItem("BASE-X")).toBe(false);
	});
});
