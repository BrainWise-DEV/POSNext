import { describe, expect, it, vi } from "vitest";

vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? s.replace(/\{(\d)\}/g, (_, i) => args[i]) : s);
});

const { offerBenefit, offerProgress, offerTypeLabel } = await import("@/utils/offerProgress");

const money = (v) => `E£${v}`;

describe("offerProgress", () => {
	it("measures a quantity offer the cart has not reached yet", () => {
		expect(offerProgress({ min_qty: 3 }, { qty: 2, amount: 30 })).toEqual({
			kind: "qty",
			have: 2,
			need: 3,
			missing: 1,
			percent: (2 / 3) * 100,
		});
	});

	it("measures an amount offer, capped at 100%", () => {
		expect(offerProgress({ min_amt: 200 }, { qty: 9, amount: 150 })).toMatchObject({
			kind: "amount",
			missing: 50,
			percent: 75,
		});
	});

	it("returns null once the minimums are met or nothing in the cart counts", () => {
		expect(offerProgress({ min_qty: 2, min_amt: 10 }, { qty: 2, amount: 30 })).toBeNull();
		expect(offerProgress({ min_qty: 2 }, { qty: 0, amount: 0 })).toBeNull();
		expect(offerProgress({}, { qty: 1, amount: 1 })).toBeNull();
	});
});

describe("offer labels", () => {
	it("leads with what the customer gets", () => {
		expect(offerBenefit({ offer: "Item Price", discount_percentage: 20 }, money)).toBe("20% off");
		expect(offerBenefit({ offer: "Item Price", discount_amount: 5 }, money)).toBe("E£5 off");
		expect(offerBenefit({ offer: "Give Product", same_item: 1, free_qty: 1 }, money)).toBe("1 free");
		expect(offerBenefit({ offer: "Give Product", free_item: "Charger", free_qty: 1 }, money)).toBe(
			"Gift: Charger"
		);
	});

	it("maps raw ERPNext offer types to labels", () => {
		expect(offerTypeLabel("Give Product")).toBe("Free gift");
		expect(offerTypeLabel("Item Price")).toBe("Price discount");
		expect(offerTypeLabel(undefined)).toBe("Discount");
	});
});
