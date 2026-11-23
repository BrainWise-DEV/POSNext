/**
 * The POS rounds the total as ERPNext does when the POS Profile rounds (D-5).
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";
import { invoiceRoundedTotal, roundBasedOnSmallestCurrencyFraction } from "@/utils/currency";

describe("roundBasedOnSmallestCurrencyFraction (frappe.utils)", () => {
	it("no smallest fraction (EGP): whole units, banker's rounding", () => {
		expect(roundBasedOnSmallestCurrencyFraction(80.5, 0, 2)).toBe(80); // U-09: rounded_total 80.00
		expect(roundBasedOnSmallestCurrencyFraction(287.5, 0, 2)).toBe(288); // U-15: 288.00
		expect(roundBasedOnSmallestCurrencyFraction(154.1, 0, 2)).toBe(154); // U-19
		expect(roundBasedOnSmallestCurrencyFraction(287.52, 0, 2)).toBe(288); // D-7 draft
		expect(roundBasedOnSmallestCurrencyFraction(80.49, 0, 2)).toBe(80);
		expect(roundBasedOnSmallestCurrencyFraction(0, 0, 2)).toBe(0);
	});
	it("a smallest fraction (CHF 0.05): exactly half goes down", () => {
		expect(roundBasedOnSmallestCurrencyFraction(10.03, 0.05, 2)).toBe(10.05);
		expect(roundBasedOnSmallestCurrencyFraction(10.02, 0.05, 2)).toBe(10);
		expect(roundBasedOnSmallestCurrencyFraction(10.025, 0.05, 3)).toBe(10.0);
		expect(roundBasedOnSmallestCurrencyFraction(10.07, 0.05, 2)).toBe(10.05);
		expect(roundBasedOnSmallestCurrencyFraction(10.08, 0.05, 2)).toBe(10.1);
	});
	it("USD 0.01 leaves a 2-dp total as it is", () => {
		expect(roundBasedOnSmallestCurrencyFraction(80.5, 0.01, 2)).toBe(80.5);
		expect(roundBasedOnSmallestCurrencyFraction(287.52, 0.01, 2)).toBe(287.52);
	});
	it("a return's negative total uses Python's modulo", () => {
		expect(roundBasedOnSmallestCurrencyFraction(-10.03, 0.05, 2)).toBe(-10.05);
		expect(roundBasedOnSmallestCurrencyFraction(-80.5, 0, 2)).toBe(-80);
	});
});

describe("invoiceRoundedTotal", () => {
	it("rounds only when the POS Profile rounds", () => {
		expect(invoiceRoundedTotal(80.5, { disable_rounded_total: 0, smallest_currency_fraction_value: 0 })).toBe(80);
		expect(invoiceRoundedTotal(80.5, { disable_rounded_total: 1 })).toBe(80.5);
		expect(invoiceRoundedTotal(80.5, null)).toBe(80.5);
		expect(invoiceRoundedTotal(10.03, { disable_rounded_total: 0, smallest_currency_fraction_value: 0.05 })).toBe(10.05);
	});
	it("does not round when the fraction is unknown (shift cached before the fraction was sent)", () => {
		expect(invoiceRoundedTotal(80.49, { disable_rounded_total: 0 })).toBe(80.49);
		expect(invoiceRoundedTotal(80.49, { disable_rounded_total: 0, smallest_currency_fraction_value: null })).toBe(80.49);
	});
});

describe("Fix round 1: a total that rounds to 0 is collected at its grand total (M2)", () => {
	it("follows ERPNext's rounded_total or grand_total", () => {
		const egp = { disable_rounded_total: 0, smallest_currency_fraction_value: 0 };
		expect(invoiceRoundedTotal(0.4, egp)).toBe(0.4);
		expect(invoiceRoundedTotal(0, egp)).toBe(0);
		expect(invoiceRoundedTotal(0.6, egp)).toBe(1);
	});
});
