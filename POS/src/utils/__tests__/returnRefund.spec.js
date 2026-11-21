import { describe, expect, it } from "vitest";
import { capRefund, emptiesOriginal, returnRefundAmount, splitRefund } from "../returnRefund";

const rounds = { disable_rounded_total: 0, smallest_currency_fraction_value: 0 };
const exact = { disable_rounded_total: 1, smallest_currency_fraction_value: 0 };

describe("returnRefundAmount (D-R2-16)", () => {
	it("refunds the rounded total of an original that rounded down", () => {
		// 00078: grand 34.50, paid 34
		expect(returnRefundAmount(34.5, rounds)).toBe(34);
	});

	it("refunds the rounded total of an original that rounded up", () => {
		// 00016: grand 287.50, paid 288
		expect(returnRefundAmount(287.5, rounds)).toBe(288);
	});

	it("refunds the exact total when the original did not round", () => {
		expect(returnRefundAmount(34.5, exact)).toBe(34.5);
		expect(returnRefundAmount(34.5, null)).toBe(34.5);
	});

	it("rounds a partial return the way ERPNext rounds the return", () => {
		expect(returnRefundAmount(11.5, rounds)).toBe(12);
		expect(returnRefundAmount(17.25, rounds)).toBe(17);
	});

	it("rounds the negative return total with a smallest fraction", () => {
		// frappe's remainder takes Python's modulo sign: -1.03 has remainder 0.02
		const fraction = { disable_rounded_total: 0, smallest_currency_fraction_value: 0.05 };
		expect(returnRefundAmount(1.03, fraction)).toBe(1.05);
		expect(returnRefundAmount(1.07, fraction)).toBe(1.05);
		expect(returnRefundAmount(1.12, fraction)).toBe(1.1);
	});

	it("keeps the total when rounding gives 0 (rounded_total or grand_total)", () => {
		expect(returnRefundAmount(0.4, rounds)).toBe(0.4);
		expect(returnRefundAmount(0, rounds)).toBe(0);
	});

	it("does not round when the fraction is unknown", () => {
		expect(returnRefundAmount(34.5, { disable_rounded_total: 0 })).toBe(34.5);
	});
});

describe("splitRefund", () => {
	it("puts a single row's refund on that row", () => {
		expect(splitRefund(34, [34])).toEqual([34]);
	});

	it("splits over the original payment modes in proportion", () => {
		expect(splitRefund(34, [20, 14])).toEqual([20, 14]);
		// Half returned
		expect(splitRefund(17, [20, 14])).toEqual([10, 7]);
	});

	it("puts the cent remainder on the largest row", () => {
		const split = splitRefund(10, [1, 1, 1]);
		expect(split.reduce((a, b) => a + b, 0)).toBeCloseTo(10, 10);
		expect(split).toEqual([3.34, 3.33, 3.33]);
	});

	it("puts everything on the first row without weights", () => {
		expect(splitRefund(34, [0, 0])).toEqual([34, 0]);
		expect(splitRefund(34, [])).toEqual([]);
	});
});

describe("capRefund (Ruling 147)", () => {
	it("refunds no more than is left on the original", () => {
		// 70 paid, 24 + 24 refunded: the last unit refunds 22, not 24
		expect(capRefund(24, 22)).toBe(22);
		// Partly paid 40 of 100
		expect(capRefund(100, 40)).toBe(40);
	});

	it("leaves a refund under the cap alone", () => {
		expect(capRefund(24, 70)).toBe(24);
	});

	it("does not cap when the refundable is unknown", () => {
		expect(capRefund(24, undefined)).toBe(24);
		expect(capRefund(24, null)).toBe(24);
	});

	it("never goes below zero", () => {
		expect(capRefund(24, 0)).toBe(0);
		expect(capRefund(24, -5)).toBe(0);
	});
});

describe("capRefund on the return that empties the original (Ruling 151)", () => {
	it("refunds the paid remainder, above its own rounded total", () => {
		// 3 x 22.50 paid at 68, 22 + 22 refunded: the last refunds 24, not 22
		expect(capRefund(22, 24, true)).toBe(24);
	});

	it("refunds the paid remainder below its own rounded total", () => {
		expect(capRefund(24, 22, true)).toBe(22);
	});

	it("keeps the refund without a known refundable", () => {
		expect(capRefund(22, undefined, true)).toBe(22);
	});
});

describe("emptiesOriginal", () => {
	const row = (overrides = {}) => ({
		rate: 22.5,
		rate_with_tax: 22.5,
		selected: true,
		return_qty: 1,
		remaining_qty: 1,
		...overrides,
	});

	it("is true when every paid row is returned in full", () => {
		expect(emptiesOriginal([row(), row({ return_qty: 2, remaining_qty: 2 })])).toBe(true);
	});

	it("ignores a free row left behind", () => {
		expect(emptiesOriginal([row(), row({ rate: 0, rate_with_tax: 0, selected: false })])).toBe(true);
	});

	it("is false when a paid row is left or partly returned", () => {
		expect(emptiesOriginal([row(), row({ selected: false })])).toBe(false);
		expect(emptiesOriginal([row({ return_qty: 1, remaining_qty: 2 })])).toBe(false);
		expect(emptiesOriginal([])).toBe(false);
	});
});
