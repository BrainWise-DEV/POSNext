/** Low-stock threshold choice and badge contrast classes. */
import { describe, expect, it } from "vitest"

globalThis.__ = (s) => s

const { DEFAULT_LOW_STOCK_THRESHOLD, getLowStockThreshold, useStock } = await import("../useStock")
const { getStockStatus, getItemStockStatus } = useStock()

describe("getLowStockThreshold", () => {
	it("prefers safety stock, then reorder level, then the default", () => {
		expect(getLowStockThreshold({ safety_stock: 3, reorder_level: 20 })).toBe(3)
		expect(getLowStockThreshold({ safety_stock: 0, reorder_level: 20 })).toBe(20)
		expect(getLowStockThreshold({})).toBe(DEFAULT_LOW_STOCK_THRESHOLD)
		expect(getLowStockThreshold(null)).toBe(DEFAULT_LOW_STOCK_THRESHOLD)
	})
})

describe("getItemStockStatus", () => {
	it("uses the item's own threshold", () => {
		expect(getItemStockStatus({ actual_qty: 6 }).level).toBe("safe")
		expect(getItemStockStatus({ actual_qty: 10, reorder_level: 24 }).level).toBe("low")
		expect(getItemStockStatus({ stock_qty: 0 }).level).toBe("out")
	})

	it("uses badge colours with at least 4.5:1 contrast on white text", () => {
		expect(getStockStatus(50).color).toBe("bg-green-700")
		expect(getStockStatus(2).color).toBe("bg-amber-700")
		expect(getStockStatus(0).color).toBe("bg-red-700")
	})
})
