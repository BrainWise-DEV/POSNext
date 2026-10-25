import { describe, expect, it, vi } from "vitest";
import { nestFreeRows, syncCartFreeItems, totalSkuQty } from "@/utils/gwpSameItemFreeRows";

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
	it("carves free qty off the paid line and marks gwp_same_item_row", () => {
		const items = [paidLine({ quantity: 3 })];
		const next = syncCartFreeItems(items, [{ item_code: "SKU-A", qty: 1, uom: "Nos" }]);

		expect(next).toHaveLength(2);
		expect(next[0].quantity).toBe(2);
		expect(next[0].is_free_item).toBeFalsy();
		expect(next[1]).toMatchObject({
			item_code: "SKU-A",
			quantity: 1,
			is_free_item: 1,
			gwp_same_item_row: 1,
			discount_source: "gwp",
			rate: 0,
		});
		expect(totalSkuQty(next, "SKU-A")).toBe(3);
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

	it("round-trips carve → clear → carve without losing scanned units", () => {
		const recalc = vi.fn();
		let items = [paidLine({ quantity: 3 })];

		items = syncCartFreeItems(
			items,
			[{ item_code: "SKU-A", qty: 1, uom: "Nos" }],
			{ recalculateItem: recalc }
		);
		expect(totalSkuQty(items, "SKU-A")).toBe(3);
		expect(items.find((i) => i.is_free_item)?.gwp_same_item_row).toBe(1);

		items = syncCartFreeItems(items, [], { recalculateItem: recalc });
		expect(items).toHaveLength(1);
		expect(items[0].quantity).toBe(3);

		items = syncCartFreeItems(
			items,
			[{ item_code: "SKU-A", qty: 1, uom: "Nos" }],
			{ recalculateItem: recalc }
		);
		expect(totalSkuQty(items, "SKU-A")).toBe(3);
		expect(items[0].quantity).toBe(2);
		expect(items[1].gwp_same_item_row).toBe(1);
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

	it("still carves when paid qty after carving meets min_qty", () => {
		const items = [paidLine({ quantity: 3 })];
		const next = syncCartFreeItems(items, [
			{ item_code: "SKU-A", qty: 1, uom: "Nos", min_qty: 2 },
		]);

		expect(next[0].quantity).toBe(2);
		expect(next[1].gwp_same_item_row).toBe(1);
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
});
