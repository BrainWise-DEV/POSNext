/**
 * D-R4-09 (a): Draft Invoices lists a held cart at the total the cart showed (154.00),
 * tax included, not at its net (134.00).
 */
import { describe, expect, it } from "vitest"
import { draftTotal, heldCartTotal } from "../draftTotal"

describe("held cart total (D-R4-09 a)", () => {
	it("adds each line's tax to its net amount", () => {
		const items = [
			{ item_code: "UIT-A", quantity: 1, rate: 100, amount: 70, tax_amount: 10.5 },
			{ item_code: "UIT-EXCL", quantity: 1, rate: 80, amount: 64, tax_amount: 9.6 },
		]
		expect(draftTotal(items)).toBe(154.1)
	})

	it("an older draft without amounts is priced at rate × qty", () => {
		expect(draftTotal([{ item_code: "A", quantity: 2, rate: 10 }])).toBe(20)
		expect(draftTotal([])).toBe(0)
	})
})

describe("held cart total with a header discount (review M8)", () => {
	it("a draft that carries the cart's grand total lists it, header discount included", () => {
		const items = [{ item_code: "UIT-C", quantity: 2, rate: 50, amount: 60, tax_amount: 9 }]
		// Promotion 60 + tax 9, an order discount of 40 on the grand total: 29.00
		expect(heldCartTotal({ items, grand_total: 29 })).toBe(29)
	})

	it("an older draft without it is summed from its lines", () => {
		expect(heldCartTotal({ items: [{ item_code: "A", amount: 70, tax_amount: 10.5 }] })).toBe(80.5)
	})
})
