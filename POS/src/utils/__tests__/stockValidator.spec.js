import { describe, it, expect, vi } from "vitest";

vi.mock("frappe-ui", () => ({ call: vi.fn() }));

import {
	checkStockAvailability,
	getCartStockQtyForItem,
	getWarehouseStockQty,
	rowStockQty,
} from "@/utils/stockValidator";

/**
 * Production case: Iphone 17 Bin qty = 6, cart has 6 phones + 1 free Aqua Water.
 * Total cart qty is 7, but stock for the phone must only see the 6 phones.
 */
const IPHONE = {
	item_code: "Iphone 17",
	item_name: "Iphone 17",
	warehouse: "Cairo - BPD",
	actual_qty: 0, // grid remaining after reserving 6
	stock_qty: 0,
	original_stock: 6, // Bin qty
	conversion_factor: 1,
	is_stock_item: 1,
};

const CART = [
	{
		item_code: "Iphone 17",
		item_name: "Iphone 17",
		quantity: 6,
		uom: "Nos",
		conversion_factor: 1,
		actual_qty: 6,
		warehouse: "Cairo - BPD",
	},
	{
		item_code: "Aqua Water",
		item_name: "Aqua Water",
		quantity: 1,
		uom: "Nos",
		conversion_factor: 1,
		is_free_item: 1,
		actual_qty: 9,
		warehouse: "Cairo - BPD",
	},
];

describe("getCartStockQtyForItem", () => {
	it("counts only the SKU being sold, not free gift rows of other items", () => {
		expect(getCartStockQtyForItem(CART, "Iphone 17")).toBe(6);
		expect(getCartStockQtyForItem(CART, "Aqua Water")).toBe(1);
	});

	it("includes free rows of the same SKU (same-item BOGO still consumes stock)", () => {
		const cart = [
			{ item_code: "Iphone 17", quantity: 5, conversion_factor: 1 },
			{ item_code: "Iphone 17", quantity: 1, conversion_factor: 1, is_free_item: 1 },
		];
		expect(getCartStockQtyForItem(cart, "Iphone 17")).toBe(6);
	});
});

describe("getWarehouseStockQty", () => {
	it("uses original_stock (Bin) instead of remaining display stock", () => {
		expect(getWarehouseStockQty(IPHONE)).toBe(6);
	});

	it("falls back to actual_qty on cart lines that store Bin qty", () => {
		expect(getWarehouseStockQty({ actual_qty: 6, stock_qty: 0 })).toBe(6);
	});
});

describe("checkStockAvailability — Iphone 17 + free Aqua Water", () => {
	it("allows keeping 6 phones in the cart when Bin qty is 6 (gift does not consume phone stock)", () => {
		const requested = getCartStockQtyForItem(CART, "Iphone 17");
		const check = checkStockAvailability(IPHONE, requested, "Cairo - BPD");
		expect(check.available).toBe(true);
		expect(check.actualQty).toBe(6);
	});

	it("blocks adding a 7th phone", () => {
		const requested = getCartStockQtyForItem(CART, "Iphone 17") + rowStockQty(IPHONE, 1);
		const check = checkStockAvailability(IPHONE, requested, "Cairo - BPD");
		expect(check.available).toBe(false);
		expect(check.error).toContain("You requested 7 units");
		expect(check.error).toContain("only 6 units available");
	});

	it("does not double-count remaining grid stock against qty already in the cart", () => {
		// Grid remaining is 1 after 5 phones reserved; Bin is 6. Adding the 6th must pass.
		const gridItem = { ...IPHONE, actual_qty: 1, stock_qty: 1, original_stock: 6 };
		const cart = [{ item_code: "Iphone 17", quantity: 5, conversion_factor: 1 }, CART[1]];
		const requested = getCartStockQtyForItem(cart, "Iphone 17") + 1;
		const check = checkStockAvailability(gridItem, requested, "Cairo - BPD");
		expect(requested).toBe(6);
		expect(check.available).toBe(true);
	});
});
