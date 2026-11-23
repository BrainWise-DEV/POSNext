import { beforeAll, describe, expect, it } from "vitest";
import {
	appliedAmountHint,
	capInvoiceDiscount,
	manualDiscountError,
	requestedDiscountAmount,
} from "../manualDiscount";

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

describe("capInvoiceDiscount (invoice-level discount, as the server caps it)", () => {
	const cap = (fields) =>
		capInvoiceDiscount({ value: 0, isPercentage: false, base: 45, maxDiscount: 0, ...fields });

	it("an amount within the limit is kept", () => {
		expect(cap({ value: 4.5, maxDiscount: 10 })).toEqual({
			amount: 4.5,
			value: 4.5,
			limited: false,
		});
	});

	it("an amount above the limit is cut to the limit of the base after line discounts", () => {
		expect(cap({ value: 5, maxDiscount: 10 })).toEqual({
			amount: 4.5,
			value: 4.5,
			limited: true,
		});
	});

	it("a percentage converts on the base after line discounts and is cut to the limit", () => {
		expect(cap({ value: 10, isPercentage: true, maxDiscount: 10 })).toEqual({
			amount: 4.5,
			value: 10,
			limited: false,
		});
		expect(cap({ value: 30, isPercentage: true, maxDiscount: 10 })).toEqual({
			amount: 4.5,
			value: 10,
			limited: true,
		});
	});

	it("0 = no limit, but never more than the base", () => {
		expect(cap({ value: 40 })).toEqual({ amount: 40, value: 40, limited: false });
		expect(cap({ value: 60 })).toEqual({ amount: 45, value: 45, limited: false });
		expect(cap({ value: 150, isPercentage: true })).toEqual({
			amount: 45,
			value: 100,
			limited: false,
		});
	});

	it("negative or empty input is no discount", () => {
		expect(cap({ value: -5 })).toEqual({ amount: 0, value: 0, limited: false });
		expect(cap({ value: "" })).toEqual({ amount: 0, value: 0, limited: false });
	});
});

describe("appliedAmountHint (G8 round 1, m-1)", () => {
	it("says what a fixed amount becomes when it does not split into whole cents a unit", () => {
		expect(appliedAmountHint({ amount: 10, qty: 3, subtotal: 150 })).toEqual({ applied: 9.99, perUnit: 3.33 });
		// Less than a cent a unit: nothing is applied, and the cashier is told so.
		expect(appliedAmountHint({ amount: 0.02, qty: 3, subtotal: 150 })).toEqual({ applied: 0, perUnit: 0 });
	});

	it("says nothing when the amount splits exactly", () => {
		expect(appliedAmountHint({ amount: 10, qty: 4, subtotal: 200 })).toBeNull();
		expect(appliedAmountHint({ amount: 0, qty: 3, subtotal: 150 })).toBeNull();
	});
});

describe("requestedDiscountAmount (G8 round 1, m-2)", () => {
	it("is the amount asked for while the line holds its own rounding of it", () => {
		const item = { discount_amount: 9.99, _unit_discount_amount: 9.99, _requested_discount_amount: 10 };
		expect(requestedDiscountAmount(item)).toBe(10);
	});

	it("is the line's amount once something else wrote it", () => {
		expect(requestedDiscountAmount({ discount_amount: 5, _unit_discount_amount: 9.99, _requested_discount_amount: 10 })).toBe(5);
		expect(requestedDiscountAmount({ discount_amount: 9.99, _unit_discount_amount: null, _requested_discount_amount: 10 })).toBe(9.99);
	});
});
