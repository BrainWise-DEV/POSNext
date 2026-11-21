/**
 * D-R2-11 (the user's D-16 decision): a customer change drops an applied line coupon.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const toast = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
	return { showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({ valid: true })),
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn() }),
}))
vi.mock("@/composables/useToast", () => ({ useToast: () => toast }))
vi.mock("@/utils/offline", () => ({
	isOffline: () => false,
	getCachedItem: vi.fn(),
}))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("../posCart")
const { stampFnfLine, isFnfLine } = await import("@/utils/friendsAndFamily")

const item = (code) => ({
	item_code: code,
	item_name: code,
	rate: 100,
	price_list_rate: 100,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
})
const coupon = { coupon_code: "L50", discount_type: "Percentage", discount_percentage: 50 }
const lineCoupon = {
	name: "L50",
	code: "L50",
	line_level: true,
	coupon,
	line_updates: [{ line_key: 0, item_code: "A", discount_percentage: 50, discount_amount: 0, rate: 50, amount: 50 }],
}

describe("D-R2-11: a customer change drops the line coupon", () => {
	let cart
	beforeEach(() => {
		toast.showWarning.mockClear()
		setActivePinia(createPinia())
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = { name: "CUST-FNF" }
		cart.addItem(item("A"))
		// F&F 30% on the line, then the 50% coupon beats it (U-18 b)
		stampFnfLine(cart.invoiceItems[0], { discount_percentage: 30, discount_amount: 30, rate: 70, applies: true })
		cart.recalculateItem(cart.invoiceItems[0])
		cart.applyDiscountToCart(lineCoupon)
		expect(cart.invoiceItems[0].coupon_code).toBe("L50")
		toast.showWarning.mockClear()
	})

	it("drops the coupon and the old customer's F&F, back to list price", async () => {
		cart.setCustomer({ name: "CUST-PLAIN" })
		const line = cart.invoiceItems[0]
		expect(line.coupon_code).toBeFalsy()
		expect(line.discount_source).not.toBe("coupon")
		expect(isFnfLine(line)).toBe(false)
		expect(line.amount).toBeCloseTo(100, 2)
		expect(cart.appliedCoupon).toBeNull()
		expect(cart.couponCode).toBeFalsy()
		expect(toast.showWarning).toHaveBeenCalledWith(expect.stringContaining("Coupon {0} removed: the customer changed"))
	})

	it("keeps the coupon when the same customer is set again (edited customer)", () => {
		cart.setCustomer({ name: "CUST-FNF", customer_name: "Edited" })
		expect(cart.invoiceItems[0].coupon_code).toBe("L50")
		expect(cart.appliedCoupon?.code).toBe("L50")
	})

	it("a loaded draft sets its customer without dropping its own coupon", () => {
		cart.setCustomer({ name: "CUST-DRAFT" }, { restoring: true })
		expect(cart.invoiceItems[0].coupon_code).toBe("L50")
		expect(cart.appliedCoupon?.code).toBe("L50")
	})
})
