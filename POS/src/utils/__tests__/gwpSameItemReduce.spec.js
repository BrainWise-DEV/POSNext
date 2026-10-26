import { describe, expect, it } from "vitest";
import { syncCartFreeItems, totalSkuQty, withCarvedQtyRestored } from "@/utils/gwpSameItemFreeRows";

// PRLE-1585-like: same item, min_qty 2, free_qty 1, not recursive, rate 100.
const MIN = 2;
const line = (quantity) => ({ item_code: "ZZFS-A", quantity, uom: "Nos", stock_uom: "Nos", rate: 100, is_free_item: 0 });
const paidDemand = (items, view) =>
	(view ? withCarvedQtyRestored(items) : items).filter((i) => !i.is_free_item).reduce((s, i) => s + i.quantity, 0);
// One evaluation pass, as posCart does: eligibility on the snapshot, then processFreeItems.
function evaluate(items, { fixed }) {
	const demand = paidDemand(items, fixed);
	const free = demand >= MIN ? [{ item_code: "ZZFS-A", qty: 1, uom: "Nos", min_qty: MIN }] : [];
	return syncCartFreeItems(items, free);
}
const rows = (c) => c.map((i) => `${i.is_free_item ? "free" : "paid"}:${i.quantity}`).join(",");
const setPaid = (c, q) => { c.find((i) => !i.is_free_item).quantity = q; return c; };

describe("same-SKU GWP: reducing qty (PRLE-1585)", () => {
	it("scan 3 → 2 paid + 1 carved free", () => {
		expect(rows(evaluate([line(3)], { fixed: true }))).toBe("paid:2,free:1");
	});

	it("BUG (old snapshot): 2 paid+1 carved, minus → 2 full-price units, no gift", () => {
		let c = evaluate([line(3)], { fixed: false });
		c = evaluate(setPaid(c, 1), { fixed: false });
		expect(rows(c)).toBe("paid:2");
	});

	it("fixed: 3 → 2 scanned units keeps the gift (2 paid + 1 free on top)", () => {
		let c = evaluate([line(3)], { fixed: true });
		c = evaluate(setPaid(c, 1), { fixed: true });
		expect(rows(c)).toBe("paid:2,free:1");
		expect(totalSkuQty(c, "ZZFS-A")).toBe(3);
	});

	it("fixed: 2 paid + 1 free on top, minus → 1 paid, no gift", () => {
		let c = evaluate([line(2)], { fixed: true });
		expect(rows(c)).toBe("paid:2,free:1");
		c = evaluate(setPaid(c, 1), { fixed: true });
		expect(rows(c)).toBe("paid:1");
	});

	it("withCarvedQtyRestored keeps row order and does not mutate", () => {
		const c = [line(1), { ...line(1), is_free_item: 1, gwp_same_item_row: 1 }];
		const v = withCarvedQtyRestored(c);
		expect(v.map((i) => i.quantity)).toEqual([2, 1]);
		expect(c[0].quantity).toBe(1);
	});
});
