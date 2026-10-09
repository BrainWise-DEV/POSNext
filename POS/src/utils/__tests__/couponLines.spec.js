import { describe, expect, it } from "vitest";
import { fixedCouponLineDiscount, hasFixedCouponDiscount, isCouponLine } from "../couponLines";

const line = (overrides = {}) => ({
	discount_source: "coupon",
	coupon_code: "SAVE",
	price_list_rate: 200,
	quantity: 3,
	coupon_fixed_discount: 99.99,
	...overrides,
});

describe("couponLines", () => {
	it("recognises coupon lines only with source and code", () => {
		expect(isCouponLine(line())).toBe(true);
		expect(isCouponLine(line({ coupon_code: null }))).toBe(false);
		expect(isCouponLine(line({ discount_source: "manual_discount" }))).toBe(false);
		expect(isCouponLine(null)).toBe(false);
	});

	it("flags fixed coupon lines only when an amount was allocated", () => {
		expect(hasFixedCouponDiscount(line())).toBe(true);
		expect(hasFixedCouponDiscount(line({ coupon_fixed_discount: 0 }))).toBe(true);
		expect(hasFixedCouponDiscount(line({ coupon_fixed_discount: null }))).toBe(false);
		expect(hasFixedCouponDiscount(line({ discount_source: "manual_discount" }))).toBe(false);
	});

	it("keeps the allocated amount when quantity grows", () => {
		expect(fixedCouponLineDiscount(line({ quantity: 10 }))).toBe(99.9);
		expect(fixedCouponLineDiscount(line({ quantity: 3 }))).toBe(99.99);
	});

	it("never exceeds the line itself when quantity shrinks", () => {
		expect(fixedCouponLineDiscount(line({ quantity: 1, price_list_rate: 50 }))).toBe(50);
		expect(fixedCouponLineDiscount(line({ quantity: 0 }))).toBe(0);
	});

	it("applies the percentage cap of a capped percentage coupon", () => {
		const capped = line({ quantity: 1, coupon_fixed_discount: 40, coupon_percentage_cap: 10 });
		expect(fixedCouponLineDiscount(capped)).toBe(20);
	});

	it("rounds down to a whole per-unit amount", () => {
		const amount = fixedCouponLineDiscount(line({ quantity: 7, coupon_fixed_discount: 100 }));
		expect(amount).toBe(99.96);
		expect(Number.isInteger(Math.round((amount / 7) * 100 * 1e6) / 1e6)).toBe(true);
	});
});
