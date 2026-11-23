/**
 * The cart line's saving label (D-R2-05, D-R2-06).
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? s.replace(/{(\d+)}/g, (m, n) => args[n]) : s)
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({ valid: true })),
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn() }),
}))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock("@/utils/offline", () => ({
	isOffline: () => false,
	getCachedItem: vi.fn(),
}))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("@/stores/posCart")
const { lineSavingTitle, paymentLineAmount, isFullyDiscountedLine } = await import("../cartLineLabels")

const item = (code) => ({
	item_code: code,
	item_name: code,
	rate: 100,
	price_list_rate: 100,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
})

describe("D-R2-05: a coupon line names only the discount that applies", () => {
	let cart
	beforeEach(() => {
		setActivePinia(createPinia())
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = { name: "CUST-1" }
		cart.addItem(item("A"))
		const line = cart.invoiceItems[0]
		// A 30% promotion on the line before the coupon
		line.discount_percentage = 30
		line.discount_source = "pricing_rule"
		cart.recalculateItem(line)
	})

	const apply = (update) =>
		cart.applyDiscountToCart({
			name: "L50",
			code: "L50",
			line_level: true,
			coupon: { coupon_code: "L50", discount_type: "Percentage", discount_percentage: 50 },
			line_updates: [{ line_key: 0, item_code: "A", discount_amount: 0, ...update }],
		})

	it("a coupon that replaced the promotion reads as the coupon alone", () => {
		apply({ discount_percentage: 50 })
		expect(lineSavingTitle(cart.invoiceItems[0])).toBe("Coupon L50")
	})

	it("a coupon stacked on the promotion (Add on top) names both", () => {
		apply({ discount_percentage: 37, stacked: 1 })
		expect(lineSavingTitle(cart.invoiceItems[0])).toBe("30% off + Coupon L50")
	})

	it("removing the coupon forgets that it was stacked", () => {
		apply({ discount_percentage: 37, stacked: 1 })
		cart.removeDiscountFromCart()
		expect(cart.invoiceItems[0].coupon_stacked).toBeFalsy()
	})
})

describe("D-R2-06: a 100% line is free, not the list amount", () => {
	const free100 = {
		item_code: "A",
		quantity: 1,
		price_list_rate: 100,
		rate: 100, // the cart keeps the list rate for display
		discount_percentage: 100,
		discount_amount: 100,
		amount: 0,
		coupon_code: "L100",
		discount_source: "coupon",
	}

	it("the payment dialog line shows 0.00", () => {
		expect(paymentLineAmount(free100)).toBe(0)
	})

	it("a line without an amount yet still shows qty × rate", () => {
		expect(paymentLineAmount({ quantity: 2, rate: 25 })).toBe(50)
	})

	it("a 100% coupon line and a 100% price-rule line read Free", () => {
		expect(isFullyDiscountedLine(free100)).toBe(true)
		expect(lineSavingTitle(free100)).toBe("Free")
		const rule = { ...free100, coupon_code: null, discount_source: "pricing_rule" }
		expect(lineSavingTitle(rule)).toBe("Free")
	})

	it("a partly discounted line and a free row are not 'fully discounted' lines", () => {
		expect(isFullyDiscountedLine({ ...free100, discount_percentage: 50, discount_amount: 50, amount: 50 })).toBe(false)
		expect(isFullyDiscountedLine({ ...free100, is_free_item: 1 })).toBe(false)
	})
})
