/**
 * D-R4-09 (d, e): the return list shows the amount paid, and per-unit discount and tax
 * read as per unit next to a multi-unit total.
 */
import { describe, expect, it } from "vitest"
import { perUnitLabel, returnListAmount } from "../returnDisplay"

describe("return dialog figures (D-R4-09 d/e)", () => {
	it("the list shows what was paid, less change: 288.00, not the 287.52 grand total", () => {
		expect(returnListAmount({ grand_total: 287.52, rounded_total: 288, paid_amount: 300, change_amount: 12 })).toBe(288)
	})

	it("an unpaid invoice shows its rounded total, else its grand total", () => {
		expect(returnListAmount({ grand_total: 287.52, rounded_total: 288, paid_amount: 0 })).toBe(288)
		expect(returnListAmount({ grand_total: 287.52 })).toBe(287.52)
	})

	it("a per-unit figure carries its unit", () => {
		expect(perUnitLabel("E£ 16.66", "Nos")).toBe("E£ 16.66/Nos")
		expect(perUnitLabel("E£ 16.66", "")).toBe("E£ 16.66")
	})
})
