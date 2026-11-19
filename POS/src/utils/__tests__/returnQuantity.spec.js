import { describe, expect, it } from "vitest"
import { initPrecision } from "../currency"
import {
	clampReturnQuantity,
	formatReturnQuantity,
	getMinReturnQuantity,
	getReturnQuantityStep,
	roundReturnQuantity,
} from "../returnQuantity"

describe("returnQuantity", () => {
	it("uses the current POS float precision for minimum quantities and button steps", () => {
		initPrecision({ float: 3 })
		expect(getMinReturnQuantity()).toBe(0.001)
		expect(getReturnQuantityStep()).toBe(0.001)

		initPrecision({ float: 2 })
		expect(getMinReturnQuantity()).toBe(0.01)
		expect(getReturnQuantityStep()).toBe(0.01)

		initPrecision({ float: 0 })
		expect(getMinReturnQuantity()).toBe(1)
		expect(getReturnQuantityStep()).toBe(1)
	})

	it("rounds floating point artifacts using float precision", () => {
		initPrecision({ float: 2 })
		expect(roundReturnQuantity(0.3 - 0.1)).toBe(0.2)
		expect(formatReturnQuantity(2)).toBe("2")
		expect(formatReturnQuantity(2.1)).toBe("2.1")
	})

	it("clamps return quantities between the minimum and remaining quantity", () => {
		initPrecision({ float: 2 })
		expect(clampReturnQuantity(0, 2.12)).toBe(0.01)
		expect(clampReturnQuantity(-1, 2.12)).toBe(0.01)
		expect(clampReturnQuantity(3, 2.12)).toBe(2.12)
		expect(clampReturnQuantity(1.235, 2.12)).toBe(1.24)
	})
})
