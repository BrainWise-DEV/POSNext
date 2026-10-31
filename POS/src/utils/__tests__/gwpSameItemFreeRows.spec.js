import { describe, expect, it, vi } from "vitest";
import { nestFreeRows, resolveFreeItemMinQty, syncCartFreeItems, totalSkuQty } from "@/utils/gwpSameItemFreeRows";

function paidLine({ item_code = "SKU-A", quantity = 3, uom = "Nos", ...rest } = {}) {
	return {
		item_code,
		item_name: item_code,
		quantity,
		uom,
		stock_uom: uom,
		conversion_factor: 1,
		rate: 10,
		is_free_item: 0,
		...rest,
	};
}

describe("syncCartFreeItems — same-SKU GWP carve/restore", () => {
	it("adds a same-SKU free row on top of the paid line (never carves)", () => {
		const items = [paidLine({ quantity: 3 })];
		const next = syncCartFreeItems(items, [{ item_code: "SKU-A", qty: 1, uom: "Nos" }]);

		expect(next).toHaveLength(2);
		expect(next[0].quantity).toBe(3);
		expect(next[0].is_free_item).toBeFalsy();
		expect(next[1]).toMatchObject({
			item_code: "SKU-A",
			quantity: 1,
			is_free_item: 1,
			gwp_same_item_row: 0,
			rate: 0,
		});
		expect(totalSkuQty(next, "SKU-A")).toBe(4);
	});

	it("restores carved qty when free rows are cleared so paid qty matches scans", () => {
		const items = [
			paidLine({ quantity: 2 }),
			{
				item_code: "SKU-A",
				quantity: 1,
				uom: "Nos",
				stock_uom: "Nos",
				is_free_item: 1,
				gwp_same_item_row: 1,
				free_qty: 1,
				rate: 0,
			},
		];

		const cleared = syncCartFreeItems(items, []);

		expect(cleared).toHaveLength(1);
		expect(cleared[0].quantity).toBe(3);
		expect(cleared[0].is_free_item).toBeFalsy();
		expect(totalSkuQty(cleared, "SKU-A")).toBe(3);
	});

	it("round-trips legacy carved row → clear → rebuild on top without losing paid units", () => {
		const recalc = vi.fn();
		let items = [
			paidLine({ quantity: 2 }),
			{ item_code: "SKU-A", quantity: 1, uom: "Nos", stock_uom: "Nos", is_free_item: 1, gwp_same_item_row: 1, rate: 0 },
		];
		items = syncCartFreeItems(items, [], { recalculateItem: recalc });
		expect(items).toHaveLength(1);
		expect(items[0].quantity).toBe(3);

		items = syncCartFreeItems(
			items,
			[{ item_code: "SKU-A", qty: 1, uom: "Nos" }],
			{ recalculateItem: recalc }
		);
		expect(items[0].quantity).toBe(3);
		expect(items[1].gwp_same_item_row).toBe(0);
		expect(totalSkuQty(items, "SKU-A")).toBe(4);
		expect(recalc).toHaveBeenCalled();
	});

	it("adds the free unit on top when carving would drop paid qty below min_qty", () => {
		const items = [paidLine({ quantity: 2 })];
		const next = syncCartFreeItems(items, [
			{ item_code: "SKU-A", qty: 1, uom: "Nos", min_qty: 2 },
		]);

		expect(next[0].quantity).toBe(2);
		expect(next[1]).toMatchObject({ quantity: 1, is_free_item: 1, gwp_same_item_row: 0 });
		expect(totalSkuQty(next, "SKU-A")).toBe(3);
	});

	it("does not carve even when paid qty minus free still meets min_qty (server adds on top)", () => {
		const items = [paidLine({ quantity: 3 })];
		const next = syncCartFreeItems(items, [
			{ item_code: "SKU-A", qty: 1, uom: "Nos", min_qty: 2 },
		]);

		expect(next[0].quantity).toBe(3);
		expect(next[1].gwp_same_item_row).toBe(0);
	});

	it("is idempotent across echo passes (no drift of paid qty)", () => {
		let items = [paidLine({ quantity: 3 })];
		for (let i = 0; i < 3; i++) {
			items = syncCartFreeItems(items, [{ item_code: "SKU-A", qty: 1, uom: "Nos", min_qty: 2 }]);
		}
		expect(items.map((x) => `${x.is_free_item ? "free" : "paid"}:${x.quantity}`)).toEqual(["paid:3", "free:1"]);
	});

	it("does not carve when the free gift is a different SKU", () => {
		const items = [paidLine({ item_code: "SKU-A", quantity: 2 })];
		const next = syncCartFreeItems(items, [
			{ item_code: "GIFT-B", qty: 1, uom: "Nos", item_name: "Gift" },
		]);

		expect(next).toHaveLength(2);
		expect(next[0].quantity).toBe(2);
		expect(next[1]).toMatchObject({
			item_code: "GIFT-B",
			quantity: 1,
			is_free_item: 1,
			gwp_same_item_row: 0,
			discount_source: "free_item",
		});
	});

	it("shows the server image on a different-SKU gift row", () => {
		const items = [paidLine({ item_code: "SKU-A", quantity: 1, image: "/files/a.jpg" })];
		const next = syncCartFreeItems(items, [
			{ item_code: "GIFT-B", qty: 1, uom: "Nos", image: "/files/gift.jpg" },
		]);

		expect(next[1].image).toBe("/files/gift.jpg");
	});

	it("ignores unmarked free rows on restore (would undercharge if GWP flag were dropped)", () => {
		// Documents the invariant: only gwp_same_item_row===1 restores.
		// A free row without the flag is treated as an added gift, not carved qty.
		const items = [
			paidLine({ quantity: 2 }),
			{
				item_code: "SKU-A",
				quantity: 1,
				uom: "Nos",
				stock_uom: "Nos",
				is_free_item: 1,
				gwp_same_item_row: 0,
				rate: 0,
			},
		];

		const cleared = syncCartFreeItems(items, []);
		expect(cleared[0].quantity).toBe(2);
		expect(totalSkuQty(cleared, "SKU-A")).toBe(2);
	});

	it("matches UOM when restoring carved qty among duplicate SKUs", () => {
		const items = [
			paidLine({ quantity: 2, uom: "Nos" }),
			paidLine({ quantity: 5, uom: "Box" }),
			{
				item_code: "SKU-A",
				quantity: 1,
				uom: "Nos",
				stock_uom: "Nos",
				is_free_item: 1,
				gwp_same_item_row: 1,
				rate: 0,
			},
		];

		const cleared = syncCartFreeItems(items, []);
		const nos = cleared.find((i) => i.uom === "Nos");
		const box = cleared.find((i) => i.uom === "Box");
		expect(nos.quantity).toBe(3);
		expect(box.quantity).toBe(5);
	});
});

describe("same-SKU buy 2 get 1 at exactly min_qty (PRLE-1585 style GWP rule)", () => {
	const offer = { name: "PRLE-1585", min_qty: 2, eligible_items: ["ZZFS-A", "ZZFS-C"] };
	const serverFree = { item_code: "ZZFS-A", qty: 1, uom: "Nos", pricing_rules: "PRLE-1585" };
	const paidEligible = (cart) =>
		cart.filter((i) => !i.is_free_item && offer.eligible_items.includes(i.item_code))
			.reduce((s, i) => s + i.quantity, 0);

	it.each([
		["string", "PRLE-1585"],
		["comma list", "PRLE-1585,PRLE-9999"],
		["array", ["PRLE-1585"]],
	])("resolves min_qty from pricing_rules as %s", (_, pr) => {
		expect(resolveFreeItemMinQty({ pricing_rules: pr }, [offer])).toBe(2);
	});

	it("falls back to the applied offer entry when the offers store lacks the rule", () => {
		expect(resolveFreeItemMinQty(serverFree, [], [{ code: "PRLE-1585", offer }])).toBe(2);
		expect(resolveFreeItemMinQty(serverFree, [], [])).toBeUndefined();
	});

	it.each([
		[2, 2, 1],
		[3, 3, 1],
		[4, 4, 1],
	])("scanned %i -> %i paid + %i free, still eligible across two passes", (scanned, paid, free) => {
		let cart = [paidLine({ item_code: "ZZFS-A", quantity: scanned })];
		for (let pass = 0; pass < 2; pass++) {
			const freeItems = [
				{ ...serverFree, min_qty: resolveFreeItemMinQty(serverFree, [], [{ code: offer.name, offer }]) },
			];
			cart = syncCartFreeItems(cart, freeItems);
			expect(paidEligible(cart)).toBe(paid);
			expect(paidEligible(cart)).toBeGreaterThanOrEqual(offer.min_qty);
			expect(cart.filter((i) => i.is_free_item).map((i) => i.quantity)).toEqual([free]);
		}
	});
});

describe("nestFreeRows — gifts under the line that earned them", () => {
	const gift = (rest) => ({ quantity: 1, uom: "Nos", stock_uom: "Nos", is_free_item: 1, rate: 0, ...rest });

	it("puts each gift right after its paid line and counts carved qty on it", () => {
		const rows = nestFreeRows([
			paidLine({ item_code: "SKU-A", quantity: 2 }),
			paidLine({ item_code: "SKU-B", quantity: 1, pricing_rules: "PR-B" }),
			gift({ item_code: "GIFT-B", pricing_rules: "PR-B" }),
			gift({ item_code: "SKU-A", gwp_same_item_row: 1 }),
		]);

		expect(rows.map((r) => r.item_code)).toEqual(["SKU-A", "SKU-A", "SKU-B", "GIFT-B"]);
		expect(rows[0]._bundledFreeQty).toBe(1);
		expect(rows[1]._giftOf).toBe("SKU-A-Nos");
		expect(rows[2]._bundledFreeQty).toBe(0);
		expect(rows[3]._giftOf).toBe("SKU-B-Nos");
	});

	it("keeps a gift with no matching line at the bottom, unnested", () => {
		const rows = nestFreeRows([gift({ item_code: "GIFT-X" }), paidLine({ item_code: "SKU-A" })]);
		expect(rows.map((r) => r.item_code)).toEqual(["SKU-A", "GIFT-X"]);
		expect(rows[1]._giftOf).toBeNull();
		expect(rows[1]._isStandaloneFreeRow).toBe(true);
	});

	it("on-top same-SKU gift (not carved) nests under its line without inflating displayed qty", () => {
		let cart = syncCartFreeItems([paidLine({ item_code: "SKU-A", quantity: 2 })], [
			{ item_code: "SKU-A", qty: 1, uom: "Nos", min_qty: 2 },
		]);
		const rows = nestFreeRows(cart);
		expect(rows.map((r) => r.item_code)).toEqual(["SKU-A", "SKU-A"]);
		expect(rows[0].quantity).toBe(2);
		expect(rows[0]._bundledFreeQty).toBe(0);
		expect(rows[1]._giftOf).toBe("SKU-A-Nos");
	});
});
