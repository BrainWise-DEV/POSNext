import { describe, expect, it, vi } from "vitest";
import { syncCartFreeItems, totalSkuQty } from "@/utils/gwpSameItemFreeRows";

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
