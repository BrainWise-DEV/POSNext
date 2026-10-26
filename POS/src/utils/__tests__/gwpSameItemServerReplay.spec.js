import { describe, expect, it } from "vitest";
import { syncCartFreeItems, totalSkuQty, withCarvedQtyRestored } from "@/utils/gwpSameItemFreeRows";

// Replays posnext_promotions apply_offers for PRLE-1585 (same-SKU GWP, min_qty 2,
// free_qty 1, not recursive) after fix/same-item-gwp-min-qty-paid-only:
// only non-free payload rows count; the gift comes back as a free_items row.
const RULE = "PRLE-1585";
const MIN = 2;
function server(payloadItems) {
	const paid = payloadItems.filter((i) => !i.is_free_item).reduce((s, i) => s + i.qty, 0);
	const ok = paid >= MIN;
	return {
		items: payloadItems,
		free_items: ok
			? [{ item_code: "ZZFS-A", qty: 1, uom: "Nos", rate: 0, is_free_item: 1, gwp_same_item_row: 1, pricing_rules: RULE }]
			: [],
		applied_pricing_rules: ok ? [RULE] : [],
	};
}
const line = (quantity) => ({ item_code: "ZZFS-A", quantity, uom: "Nos", stock_uom: "Nos", rate: 100, is_free_item: 0 });
const rows = (c) => c.map((i) => `${i.is_free_item ? "free" : "paid"}:${i.quantity}`).join(",");
const paidDemand = (c) => withCarvedQtyRestored(c).filter((i) => !i.is_free_item).reduce((s, i) => s + i.quantity, 0);

// One posCart pass: buildOfferEvaluationPayload → server → processFreeItems.
// "Offer removed" fires when a previously applied rule disappears.
function pass(cart, state) {
	const payload = withCarvedQtyRestored(cart).map((i) => ({ item_code: i.item_code, qty: i.quantity, is_free_item: i.is_free_item || 0 }));
	const res = server(payload);
	const applied = res.applied_pricing_rules.includes(RULE);
	if (state.applied && !applied) state.removed.push(paidDemand(cart));
	state.applied = applied;
	const free = res.free_items.map((f) => ({ ...f, min_qty: MIN }));
	return syncCartFreeItems(cart, free);
}
function settle(cart, state) {
	let c = pass(cart, state);
	const before = rows(c);
	c = pass(c, state); // echo pass with free rows must be a no-op
	expect(rows(c)).toBe(before);
	return c;
}
const paidLine = (c) => c.find((i) => !i.is_free_item);

describe("PRLE-1585 replay against paid-only server", () => {
	it("scan 1 → no gift", () => {
		const s = { applied: false, removed: [] };
		expect(rows(settle([line(1)], s))).toBe("paid:1");
	});
	it("scan 2 → 2 paid + 1 free on top; echo pass stable", () => {
		const s = { applied: false, removed: [] };
		const c = settle([line(2)], s);
		expect(rows(c)).toBe("paid:2,free:1");
		expect(s.removed).toEqual([]);
	});
	it("scan 1→2→3, then reduce, without spurious Offer removed", () => {
		const s = { applied: false, removed: [] };
		let c = settle([line(1)], s);
		paidLine(c).quantity += 1;
		c = settle(c, s);
		expect(rows(c)).toBe("paid:2,free:1");
		paidLine(c).quantity += 1; // 3rd scan: the gift unit itself → carved
		c = settle(c, s);
		expect(rows(c)).toBe("paid:2,free:1");
		expect(totalSkuQty(c, "ZZFS-A")).toBe(3);
		expect(s.removed).toEqual([]);
		paidLine(c).quantity -= 1; // 3 scanned → 2 scanned
		c = settle(c, s);
		expect(rows(c)).toBe("paid:2,free:1");
		expect(s.removed).toEqual([]);
		paidLine(c).quantity -= 1; // 2 → 1: legitimately no longer qualifies
		c = settle(c, s);
		expect(rows(c)).toBe("paid:1");
		expect(s.removed).toEqual([1]);
	});
	it("scan 4 → 3 paid + 1 free", () => {
		const s = { applied: false, removed: [] };
		expect(rows(settle([line(4)], s))).toBe("paid:3,free:1");
	});
});
