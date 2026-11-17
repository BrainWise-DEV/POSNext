import { beforeAll, describe, expect, it } from "vitest";
import { manualDiscountError } from "../manualDiscount";

beforeAll(() => {
	globalThis.__ = (s, args) => (args ? s.replace(/\{(\d)\}/g, (_, i) => args[i]) : s);
});

const line = (fields) => ({
	listPrice: 50,
	rate: 50,
	qty: 1,
	discountPercentage: 0,
	discountAmount: 0,
	maxDiscount: 0,
	...fields,
});

describe("manualDiscountError", () => {
	it("allows no discount", () => {
		expect(manualDiscountError(line({}))).toBeNull();
	});

	it("refuses a 100% discount, by percentage or amount", () => {
		expect(manualDiscountError(line({ discountPercentage: 100 }))).toContain("less than 100%");
		expect(manualDiscountError(line({ discountAmount: 50 }))).toContain("less than 100%");
	});

	it("allows any discount below 100% when there is no limit", () => {
		expect(manualDiscountError(line({ discountPercentage: 99 }))).toBeNull();
	});

	it("applies the maximum to discount edits", () => {
		expect(manualDiscountError(line({ discountPercentage: 10, maxDiscount: 10 }))).toBeNull();
		expect(manualDiscountError(line({ discountPercentage: 11, maxDiscount: 10 }))).toContain(
			"11.00% exceeds maximum allowed discount of 10%"
		);
	});

	it("counts a rate edit and a discount together against the maximum", () => {
		// 50 → 45 (10%) then 10% off → 40.5: 19% off list price
		expect(
			manualDiscountError(line({ rate: 45, discountPercentage: 10, maxDiscount: 15 }))
		).toContain("19.00%");
	});
});
