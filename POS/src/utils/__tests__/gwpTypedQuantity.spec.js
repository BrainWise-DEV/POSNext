import { describe, expect, it } from "vitest";
import {
	getDisplayQuantity,
	resolvePaidQuantityFromDisplay,
	syncCartFreeItems,
} from "@/utils/gwpSameItemFreeRows";

// Typed qty in InvoiceCart goes display → paid via resolvePaidQuantityFromDisplay,
// then the same update-quantity path as +/-. They must round-trip.
const line = (extra = {}) => ({ item_code: "ZZFS-A", quantity: 2, uom: "Nos", stock_uom: "Nos", rate: 100, is_free_item: 0, ...extra });
const rows = (c) => c.map((i) => `${i.is_free_item ? "free" : "paid"}:${i.quantity}`).join(",");
const evaluate = (c) => {
	const paid = c.filter((i) => !i.is_free_item).reduce((s, i) => s + i.quantity, 0);
	return syncCartFreeItems(c, paid >= 2 ? [{ item_code: "ZZFS-A", qty: 1, uom: "Nos", min_qty: 2 }] : []);
};
const typeQty = (c, value) => {
	const paid = c.find((i) => !i.is_free_item);
	paid.quantity = resolvePaidQuantityFromDisplay(paid, Number.parseFloat(value));
	return evaluate(c);
};

describe("typed paid qty (PRLE-1585)", () => {
	it.each([
		["plain line", {}],
		["server-stamped free_item line", { discount_source: "free_item", free_qty: 1 }],
		["gwp line", { discount_source: "gwp", gwp_free_qty: 1, free_qty: 1 }],
	])("display ↔ paid round-trips for %s", (_, extra) => {
		const item = line(extra);
		for (const q of [1, 2, 3, 4]) {
			item.quantity = q;
			expect(resolvePaidQuantityFromDisplay(item, getDisplayQuantity(item))).toBe(q);
		}
	});

	it("typed qty on a free_item-stamped line is the paid qty (was: free_qty subtracted)", () => {
		expect(resolvePaidQuantityFromDisplay(line({ discount_source: "free_item", free_qty: 1 }), 1)).toBe(1);
		expect(resolvePaidQuantityFromDisplay(line({ discount_source: "free_item", free_qty: 1 }), 3)).toBe(3);
	});

	it("bundled display subtracts the bundled free units", () => {
		const item = line({ _bundledFreeQty: 1 });
		expect(getDisplayQuantity(item)).toBe(3);
		expect(resolvePaidQuantityFromDisplay(item, 3)).toBe(2);
	});

	it("type 3 from 1, then type 1 from 3: gift on top then dropped", () => {
		let c = evaluate([line({ quantity: 1 })]);
		c = typeQty(c, "3");
		expect(rows(c)).toBe("paid:3,free:1");
		c = typeQty(c, "1");
		expect(rows(c)).toBe("paid:1");
	});

	it("type 1 from 2 paid + 1 free drops the offer (no restore bounce)", () => {
		let c = evaluate([line({ quantity: 2 })]);
		expect(rows(c)).toBe("paid:2,free:1");
		c = typeQty(c, "1");
		expect(rows(c)).toBe("paid:1");
	});
});
