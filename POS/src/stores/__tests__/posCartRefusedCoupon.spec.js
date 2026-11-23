/**
 * A coupon used up by another cashier between Apply and Checkout: the server refuses
 * it as "Coupon Not Applicable" and the cart drops it (UI test D-R3-08).
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? s.replace(/\{(\d+)\}/g, (_, i) => args[i]) : s)
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: () => ({ submit: vi.fn(async () => ({})), reload: vi.fn(), fetch: vi.fn() }),
}))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("../posCart")
const { parseError } = await import("@/utils/errorHandler")

const REFUSAL = {
	httpStatus: 417,
	exc_type: "CouponNotApplicableError",
	_server_messages: JSON.stringify([
		JSON.stringify({ message: "Coupon UIT-MAX1 has reached its usage limit", title: "Coupon Not Applicable" }),
	]),
}

describe("D-R3-08: a coupon refused at Checkout", () => {
	it("is read as Coupon Not Applicable, with the server's reason", () => {
		const context = parseError(REFUSAL)
		expect(context.couponRefused).toBe(true)
		expect(context.title).toBe("Coupon Not Applicable")
		expect(context.message).toBe("Coupon UIT-MAX1 has reached its usage limit")
	})

	it("another validation error is not a coupon refusal", () => {
		const context = parseError({ httpStatus: 417, exc_type: "ValidationError", messages: ["Something else"] })
		expect(context.couponRefused).toBeFalsy()
	})

	describe("the cart", () => {
		let cart
		beforeEach(() => {
			setActivePinia(createPinia())
			cart = usePOSCartStore()
			cart.posProfile = "POS-1"
			cart.customer = "CUST-1"
			cart.addItem({
				item_code: "A",
				item_name: "A",
				rate: 100,
				price_list_rate: 100,
				uom: "Nos",
				stock_uom: "Nos",
				conversion_factor: 1,
			})
		})

		it("drops a whole-cart coupon and its discount", () => {
			cart.applyDiscountToCart({ name: "UIT-MAX1", code: "UIT-MAX1", percentage: 10, type: "percentage" })
			expect(cart.couponCode).toBe("UIT-MAX1")
			expect(cart.appliedCoupon).toBeTruthy()
			expect(cart.additionalDiscount).toBeGreaterThan(0)
			expect(cart.dropRefusedCoupon()).toBe(true)
			expect(cart.appliedCoupon).toBeNull()
			expect(cart.couponCode).toBeNull()
			expect(cart.additionalDiscount).toBe(0)
		})

		it("does nothing without a coupon", () => {
			expect(cart.dropRefusedCoupon()).toBe(false)
		})
	})
})
