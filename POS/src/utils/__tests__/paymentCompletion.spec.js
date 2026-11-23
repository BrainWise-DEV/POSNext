/**
 * Completing the payment dialog, including a zero-total sale (D-14).
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";
import { canCompletePayment, isZeroTotal } from "@/utils/paymentCompletion";

describe("canCompletePayment", () => {
	it("a 0.00 sale (100% coupon, only free rows) completes with no payment", () => {
		expect(canCompletePayment({ invoiceTotal: 0, remaining: 0, entryCount: 0 })).toBe(true);
		// Partial payment allowed or not, the answer is the same.
		expect(canCompletePayment({ invoiceTotal: 0, entryCount: 0, allowPartialPayment: true })).toBe(true);
	});

	it("a zero-total sale still needs its sales person", () => {
		expect(canCompletePayment({ invoiceTotal: 0, salesPersonValid: false })).toBe(false);
	});

	it("a sale above zero still needs a payment entry", () => {
		expect(canCompletePayment({ invoiceTotal: 0.4, remaining: 0, entryCount: 0 })).toBe(false);
		expect(canCompletePayment({ invoiceTotal: 50, remaining: 0, entryCount: 1, totalPaid: 50 })).toBe(true);
		expect(canCompletePayment({ invoiceTotal: 50, remaining: 10, entryCount: 1, totalPaid: 40 })).toBe(false);
	});

	it("keeps the partial, write-off and receivable rules", () => {
		expect(canCompletePayment({ invoiceTotal: 50, remaining: 10, entryCount: 1, totalPaid: 40, allowPartialPayment: true })).toBe(true);
		expect(canCompletePayment({ invoiceTotal: 50, remaining: 1, entryCount: 1, totalPaid: 49, writeOffCovers: true })).toBe(true);
		expect(canCompletePayment({ invoiceTotal: 50, remaining: 50, entryCount: 0, receivableAccount: true, receivableLimit: 50 })).toBe(true);
	});
});

describe("isZeroTotal", () => {
	it("is zero to the cent only", () => {
		expect(isZeroTotal(0)).toBe(true);
		expect(isZeroTotal(0.001)).toBe(true);
		expect(isZeroTotal(0.01)).toBe(false);
		expect(isZeroTotal(-5)).toBe(false);
	});
});

describe("Fix round 1: zero threshold from currency precision (M3)", () => {
	it("on a 3-dp currency 0.004 is not zero", () => {
		expect(isZeroTotal(0.004, 3)).toBe(false);
		expect(isZeroTotal(0.0004, 3)).toBe(true);
		expect(canCompletePayment({ invoiceTotal: 0.004, entryCount: 0, precision: 3 })).toBe(false);
	});
});
