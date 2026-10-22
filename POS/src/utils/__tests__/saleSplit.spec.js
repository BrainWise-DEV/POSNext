import { describe, expect, it } from "vitest";

import {
	allocateQty,
	expectedAllocation,
	previewSaleSplit,
	previewWarehousePick,
	saleRowKey,
	splitSubmissionItems,
	transferByCompany,
} from "../saleSplit";

const scope = {
	native: "UTAMA - MJP",
	company: "MJP PT",
	companyByWarehouse: {
		"UTAMA - MJP": { company: "MJP PT", abbr: "MJP" },
		"UTAMA - BISC": { company: "BISC CV", abbr: "BISC" },
	},
};

const stock = {
	A: { "UTAMA - MJP": 20, "UTAMA - BISC": 10 },
	B: { "UTAMA - MJP": 0, "UTAMA - BISC": 5 },
};
const stockOf = (code) => stock[code] || {};

const row = (overrides) => ({
	item_code: "A",
	uom: "PCS",
	quantity: 1,
	conversion_factor: 1,
	warehouse: "UTAMA - MJP",
	amount: 100,
	...overrides,
});

describe("allocateQty", () => {
	it("fills the first warehouse before spilling", () => {
		const remaining = { W1: 3, W2: 10 };
		expect(allocateQty(5, 1, ["W1", "W2"], remaining)).toEqual([
			{ warehouse: "W1", qty: 3 },
			{ warehouse: "W2", qty: 2 },
		]);
		expect(remaining).toEqual({ W1: 0, W2: 8 });
	});

	it("leaves a shortfall on the first warehouse", () => {
		expect(allocateQty(5, 1, ["W1", "W2"], { W1: 1, W2: 1 })).toEqual([
			{ warehouse: "W1", qty: 4 },
			{ warehouse: "W2", qty: 1 },
		]);
	});

	it("draws stock in stock UOM", () => {
		expect(allocateQty(2, 12, ["W1", "W2"], { W1: 12, W2: 24 })).toEqual([
			{ warehouse: "W1", qty: 1 },
			{ warehouse: "W2", qty: 1 },
		]);
	});
});

describe("previewSaleSplit", () => {
	it("keeps a basket the session warehouse covers on one invoice", () => {
		const split = previewSaleSplit([row({ quantity: 5 })], scope, stockOf);
		expect(split.groups.map((g) => g.company)).toEqual(["MJP PT"]);
	});

	it("spills a row over the branch and splits the sale per company", () => {
		const cart = [row({ quantity: 25, amount: 2500 })];
		const split = previewSaleSplit(cart, scope, stockOf);
		expect(split.rows.get(saleRowKey(cart[0])).map((c) => [c.abbr, c.qty])).toEqual([
			["MJP", 20],
			["BISC", 5],
		]);
		expect(split.groups).toEqual([
			{ company: "MJP PT", abbr: "MJP", amount: 2000 },
			{ company: "BISC CV", abbr: "BISC", amount: 500 },
		]);
	});

	it("draws a hand-picked branch warehouse first and spills the rest", () => {
		// One cart row per item: 2 added from the store, 15 picked from BISC
		const cart = [row({ quantity: 17, warehouse: "UTAMA - BISC", warehouse_manual: true })];
		const split = previewSaleSplit(cart, scope, stockOf);
		expect(split.rows.get(saleRowKey(cart[0])).map((c) => [c.abbr, c.qty])).toEqual([
			["BISC", 10],
			["MJP", 7],
		]);
	});

	it("spills a hand-picked warehouse that has run out", () => {
		const cart = [row({ item_code: "B", quantity: 2, warehouse_manual: true })];
		const split = previewSaleSplit(cart, scope, stockOf);
		expect(split.groups.map((g) => g.abbr)).toEqual(["BISC"]);
	});

	it("draws the store first when store_stock_first is on", () => {
		const cart = [row({ quantity: 17, warehouse: "UTAMA - BISC", warehouse_manual: true })];
		const split = previewSaleSplit(cart, scope, stockOf, { storeStockFirst: true });
		expect(split.rows.get(saleRowKey(cart[0])).map((c) => [c.abbr, c.qty])).toEqual([
			["MJP", 17],
		]);
	});

	it("never moves a row from an SPG order", () => {
		const cart = [row({ item_code: "B", quantity: 2, pos_order_row: "R1" })];
		const split = previewSaleSplit(cart, scope, stockOf);
		expect(split.groups.map((g) => g.abbr)).toEqual(["MJP"]);
	});

	it("bills a tinted row at its own price - HPP tinta is a cost", () => {
		const cart = [row({ item_code: "B", quantity: 2, tinting: { job: "J1", hpp_tinta: 30 } })];
		const split = previewSaleSplit(cart, scope, stockOf);
		expect(split.groups).toEqual([{ company: "BISC CV", abbr: "BISC", amount: 100 }]);
		expect(split.company).toBe("MJP PT");
	});

	it("rows of the same item share one stock balance", () => {
		const cart = [row({ quantity: 15 }), row({ quantity: 10, uom: "PCS2" })];
		const split = previewSaleSplit(cart, scope, stockOf);
		expect(split.rows.get(saleRowKey(cart[1])).map((c) => [c.abbr, c.qty])).toEqual([
			["MJP", 5],
			["BISC", 5],
		]);
	});

	it("is empty when the branch has a single warehouse", () => {
		const single = {
			...scope,
			companyByWarehouse: { "UTAMA - MJP": scope.companyByWarehouse["UTAMA - MJP"] },
		};
		expect(previewSaleSplit([row()], single, stockOf).groups).toEqual([]);
	});
});

describe("splitSubmissionItems", () => {
	it("splits submission rows per company with add ons on the base's company", () => {
		const cart = [row({ quantity: 25, amount: 2500 })];
		const split = previewSaleSplit(cart, scope, stockOf);
		const items = [
			{
				item_code: "A",
				uom: "PCS",
				qty: 25,
				rate: 100,
				discount_amount: 50,
				custom_addon_key: "k1",
			},
			{ item_code: "INK", qty: 1, rate: 30, custom_addon_parent_key: "k1" },
		];
		const groups = splitSubmissionItems(items, split);
		expect(
			groups.map((g) => [
				g.abbr,
				g.items.map((i) => [i.item_code, i.qty, i.discount_amount]),
			])
		).toEqual([
			[
				"MJP",
				[
					["A", 20, 40],
					["INK", 1, undefined],
				],
			],
			["BISC", [["A", 5, 10]]],
		]);
	});
});

describe("server allocation and SPG order lines", () => {
	it("shows the server's allocation instead of the local one", () => {
		const cart = [row({ quantity: 3 })];
		const allocation = [
			[
				{ warehouse: "UTAMA - BISC", qty: 1 },
				{ warehouse: "UTAMA - MJP", qty: 2 },
			],
		];
		const split = previewSaleSplit(cart, scope, stockOf, { allocation });
		expect(split.rows.get(saleRowKey(cart[0])).map((c) => [c.abbr, c.qty])).toEqual([
			["BISC", 1],
			["MJP", 2],
		]);
		expect(expectedAllocation(cart, split)).toEqual([
			["A", "UTAMA - BISC", 1],
			["A", "UTAMA - MJP", 2],
		]);
	});

	it("keeps an SPG order line's locked split and bills each part on its own", () => {
		const chunks = [
			{ warehouse: "UTAMA - MJP", qty: 2 },
			{ warehouse: "UTAMA - BISC", qty: 1 },
		];
		const cart = [row({ quantity: 3, pos_order_row: true, pos_order_chunks: chunks })];
		const split = previewSaleSplit(cart, scope, stockOf);
		expect(split.rows.get(saleRowKey(cart[0])).map((c) => [c.abbr, c.qty])).toEqual([
			["MJP", 2],
			["BISC", 1],
		]);
		const items = [
			{ item_code: "A", uom: "PCS", qty: 2, warehouse: "UTAMA - MJP" },
			{ item_code: "A", uom: "PCS", qty: 1, warehouse: "UTAMA - BISC" },
		];
		expect(
			splitSubmissionItems(items, split).map((g) => [g.abbr, g.items.map((i) => i.qty)])
		).toEqual([
			["MJP", [2]],
			["BISC", [1]],
		]);
	});

	it("takes the store stock first, then the warehouse picked outside the branch", () => {
		const cart = [
			row({ item_code: "B", quantity: 7, warehouse: "LUAR - MJP", warehouse_manual: true }),
		];
		const split = previewSaleSplit(cart, scope, stockOf, { storeStockFirst: true });
		expect(split.rows.get(saleRowKey(cart[0])).map((c) => [c.warehouse, c.qty])).toEqual([
			["UTAMA - BISC", 5],
			["LUAR - MJP", 2],
		]);
	});

	it("splits a one-warehouse branch when the cashier picked a warehouse outside it", () => {
		const single = {
			...scope,
			companyByWarehouse: { "UTAMA - MJP": scope.companyByWarehouse["UTAMA - MJP"] },
		};
		const cart = [row({ quantity: 25, warehouse: "LUAR - MJP", warehouse_manual: true })];
		const split = previewSaleSplit(cart, single, stockOf, { storeStockFirst: true });
		expect(split.rows.get(saleRowKey(cart[0])).map((c) => [c.warehouse, c.qty])).toEqual([
			["UTAMA - MJP", 20],
			["LUAR - MJP", 5],
		]);
	});

	it("sends no allocation when the session sells from one warehouse", () => {
		const single = {
			...scope,
			companyByWarehouse: { "UTAMA - MJP": scope.companyByWarehouse["UTAMA - MJP"] },
		};
		expect(expectedAllocation([row()], previewSaleSplit([row()], single, stockOf))).toBeNull();
	});
});

describe("previewWarehousePick", () => {
	const warehouses = [
		{ warehouse: "TOKO", tier: "native", stock_qty: 2 },
		{ warehouse: "GUDANG", tier: "branch", stock_qty: 10 },
		{ warehouse: "LUAR", tier: "outside", stock_qty: 5 },
	];

	it("takes the store stock first and the rest from the picked warehouse", () => {
		const pick = previewWarehousePick(warehouses, 3, {
			selected: "GUDANG",
			manual: true,
			storeStockFirst: true,
		});
		expect(pick).toEqual({
			chunks: [
				{ warehouse: "TOKO", qty: 2 },
				{ warehouse: "GUDANG", qty: 1 },
			],
			shortfall: 0,
		});
	});

	it("draws the hand-picked warehouse first when store_stock_first is off", () => {
		const pick = previewWarehousePick(warehouses, 3, { selected: "GUDANG", manual: true });
		expect(pick.chunks).toEqual([{ warehouse: "GUDANG", qty: 3 }]);
	});

	it("reaches a warehouse outside the branch only when picked", () => {
		expect(previewWarehousePick(warehouses, 14).shortfall).toBe(2);
		const pick = previewWarehousePick(warehouses, 14, {
			selected: "LUAR",
			manual: true,
			storeStockFirst: true,
		});
		expect(pick.chunks).toEqual([
			{ warehouse: "TOKO", qty: 2 },
			{ warehouse: "GUDANG", qty: 10 },
			{ warehouse: "LUAR", qty: 2 },
		]);
		expect(pick.shortfall).toBe(0);
	});
});

describe("transferByCompany", () => {
	const groups = [
		{ company: "MJP PT", amount: 800000 },
		{ company: "BISC CV", amount: 450000 },
	];

	it("sends each company its own invoice total to its own account", () => {
		expect(transferByCompany(groups, { "Transfer BCA": 1250000 }, 1250000)).toEqual([
			{ company: "MJP PT", mode: "Transfer BCA", amount: 800000 },
			{ company: "BISC CV", mode: "Transfer BCA", amount: 450000 },
		]);
	});

	it("splits a basket over two banks in the basket's proportions, rest to the session company", () => {
		const rows = transferByCompany(groups, { A: 750000, B: 500000 }, 1250000);
		expect(rows.filter((r) => r.company === "BISC CV")).toEqual([
			{ company: "BISC CV", mode: "A", amount: 270000 },
			{ company: "BISC CV", mode: "B", amount: 180000 },
		]);
		expect(rows.filter((r) => r.company === "MJP PT").map((r) => r.amount)).toEqual([480000, 320000]);
	});

	it("applies the invoice discount and keeps a single company on one account", () => {
		expect(transferByCompany(groups, { A: 1000000 }, 1000000)[1].amount).toBe(360000);
		expect(transferByCompany([groups[0]], { A: 800000 }, 800000)).toEqual([
			{ company: "MJP PT", mode: "A", amount: 800000 },
		]);
	});
});
