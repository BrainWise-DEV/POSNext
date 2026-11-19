import { describe, expect, it } from "vitest";
import { syncCartFreeItems, totalSkuQty, withCarvedQtyRestored } from "@/utils/gwpSameItemFreeRows";

// PRLE-1585-like: same item, min_qty 2, free_qty 1, not recursive, rate 100.
// Server qualifies on paid qty only and returns the gift as a free_items row on top.
const MIN = 2;
const line = (quantity) => ({ item_code: "ZZFS-A", quantity, uom: "Nos", stock_uom: "Nos", rate: 100, is_free_item: 0 });
const paidDemand = (items) =>
	withCarvedQtyRestored(items).filter((i) => !i.is_free_item).reduce((s, i) => s + i.quantity, 0);
function evaluate(items) {
	const free = paidDemand(items) >= MIN ? [{ item_code: "ZZFS-A", qty: 1, uom: "Nos", min_qty: MIN }] : [];
	return syncCartFreeItems(items, free);
}
const rows = (c) => c.map((i) => `${i.is_free_item ? "free" : "paid"}:${i.quantity}`).join(",");
const setPaid = (c, q) => { c.find((i) => !i.is_free_item).quantity = q; return c; };

describe("same-SKU GWP: changing paid qty (PRLE-1585)", () => {
	it.each([[1, "paid:1"], [2, "paid:2,free:1"], [3, "paid:3,free:1"], [4, "paid:4,free:1"]])(
		"paid %i → %s",
		(q, expected) => {
			expect(rows(evaluate([line(q)]))).toBe(expected);
		}
	);

	it("up 1→4 then down 4→1 mirrors, gift drops only at 1", () => {
		let c = evaluate([line(1)]);
		const seen = [];
		for (const q of [2, 3, 4, 3, 2, 1]) {
			c = evaluate(setPaid(c, q));
			seen.push(rows(c));
		}
		expect(seen).toEqual([
			"paid:2,free:1", "paid:3,free:1", "paid:4,free:1",
			"paid:3,free:1", "paid:2,free:1", "paid:1",
		]);
		expect(totalSkuQty(c, "ZZFS-A")).toBe(1);
	});

	it("legacy carved row: restored once, not re-carved (no 1→2 bounce)", () => {
		const c = [line(2), { ...line(1), is_free_item: 1, gwp_same_item_row: 1 }];
		// cashier sets paid to 1: restore yields 2 once, from then on paid is authoritative
		let next = evaluate(c);
		expect(rows(next)).toBe("paid:3,free:1");
		next = evaluate(setPaid(next, 1));
		expect(rows(next)).toBe("paid:1");
	});

	it("withCarvedQtyRestored keeps row order and does not mutate", () => {
		const c = [line(1), { ...line(1), is_free_item: 1, gwp_same_item_row: 1 }];
		const v = withCarvedQtyRestored(c);
		expect(v.map((i) => i.quantity)).toEqual([2, 1]);
		expect(c[0].quantity).toBe(1);
	});

	it("withCarvedQtyRestored ignores on-top free rows (paid lines alone count)", () => {
		const c = evaluate([line(2)]);
		expect(paidDemand(c)).toBe(2);
	});
});
