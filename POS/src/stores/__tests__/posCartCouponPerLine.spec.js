/**
 * A coupon and Friends & Family share one cart: each line has exactly one of them.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({ valid: true })),
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn() }),
}))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({
		showSuccess: vi.fn(),
		showError: vi.fn(),
		showWarning: vi.fn(),
		showInfo: vi.fn(),
	}),
}))
vi.mock("@/utils/offline", () => ({
	isOffline: () => false,
	getCachedItem: vi.fn(),
}))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("../posCart")
const { stampFnfLine, isFnfLine, lineCouponFnfView, buildFnfCartMessages } = await import("@/utils/friendsAndFamily")

const item = (code) => ({
	item_code: code,
	item_name: code,
	rate: 100,
	price_list_rate: 100,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
})
const coupon20 = { coupon_code: "C20", discount_type: "Percentage", discount_percentage: 20 }
const lineUpdate = (key, code, pct) => ({
	line_key: key,
	item_code: code,
	discount_percentage: pct,
	discount_amount: 0,
	rate: 100 - pct,
	amount: 100 - pct,
	coupon_code: "C20",
})
const lineDiscount = (cart) =>
	cart.invoiceItems.reduce((sum, i) => sum + (i.price_list_rate * i.quantity - i.amount), 0)

describe("coupon vs Friends & Family per line", () => {
	let cart
	beforeEach(() => {
		setActivePinia(createPinia())
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = "CUST-1"
		cart.addItem(item("A")) // not covered by F&F
		cart.addItem(item("B")) // F&F 30%
		stampFnfLine(cart.invoiceItems[1], {
			discount_percentage: 30,
			discount_amount: 30,
			rate: 70,
			applies: true,
		})
		cart.recalculateItem(cart.invoiceItems[1])
	})

	const applyCoupon = (updates) =>
		cart.applyDiscountToCart({
			name: "C20",
			code: "C20",
			line_level: true,
			coupon: coupon20,
			line_updates: updates,
		})

	it("per_line_coupon_keeps_fnf_on_other_lines", () => {
		// 20 on A beats nothing; 20 on B loses to F&F 30, so the server gives the coupon line A only
		applyCoupon([lineUpdate(0, "A", 20)])
		const [a, b] = cart.invoiceItems
		expect(a.discount_source).toBe("coupon")
		expect(a.coupon_code).toBe("C20")
		expect(isFnfLine(b)).toBe(true)
		expect(b.coupon_code).toBeFalsy()
		expect(lineDiscount(cart)).toBeCloseTo(50, 2)
		expect(cart.additionalDiscount).toBe(0)
		expect(cart.fnfCouponOverride).toBeNull()
	})

	it("order_level_coupon_uses_header", () => {
		cart.applyDiscountToCart({
			name: "C50",
			code: "C50",
			percentage: 0,
			amount: 50,
			suppress_friends_and_family: true,
			coupon: { coupon_code: "C50", discount_type: "Amount", discount_amount: 50 },
		})
		expect(cart.additionalDiscount).toBe(50)
		expect(cart.invoiceItems.some(isFnfLine)).toBe(false)
		expect(cart.invoiceItems.every((i) => i.coupon_code == null)).toBe(true)
		expect(cart.fnfCouponOverride?.code).toBe("C50")
	})

	const fnfResult = {
		eligible: true,
		discountPercentage: 30,
		appliedCount: 1,
		lines: [{ idx: 1, applies: true, discount_amount: 30 }],
		caps: { active: true, fnf_applied_total: 30, monthly_remaining: 1850, monthly_remaining_after: 1820 },
	}

	it("D-15: a line coupon that took every F&F line mutes F&F", () => {
		// U-18 b: the coupon (40%) beats F&F 30% on B, the only F&F line
		cart.applyDiscountToCart({
			name: "C20",
			code: "C20",
			line_level: true,
			coupon: coupon20,
			line_updates: [lineUpdate(1, "B", 40)],
			fnf_message: { message_en: "Coupon C20 (40%) is better than Friends & Family (30%)" },
		})
		expect(cart.appliedCoupon.fnf_message.message_en).toContain("better")
		expect(cart.fnfCouponOverride).toBeNull() // F&F is not dropped from other lines
		const view = lineCouponFnfView({ result: fnfResult, items: cart.invoiceItems, appliedCoupon: cart.appliedCoupon })
		expect(view.override).toEqual({ code: "C20" })
		const messages = buildFnfCartMessages({ result: view.result, couponOverride: view.override })
		expect(messages).toHaveLength(1)
		expect(messages[0].text).toContain("applied instead of Friends & Family")
		expect(messages[0].text).toContain("never combined")
	})

	it("D-15: a line coupon that took some F&F lines counts only the lines that kept F&F", () => {
		cart.addItem(item("C"))
		stampFnfLine(cart.invoiceItems[2], { discount_percentage: 30, discount_amount: 30, rate: 70, applies: true })
		cart.recalculateItem(cart.invoiceItems[2])
		const result = {
			...fnfResult,
			appliedCount: 2,
			lines: [
				{ idx: 1, applies: true, discount_amount: 30 },
				{ idx: 2, applies: true, discount_amount: 30 },
			],
			caps: { active: true, fnf_applied_total: 60, monthly_remaining: 1850, monthly_remaining_after: 1790 },
		}
		applyCoupon([lineUpdate(1, "B", 40)])
		const view = lineCouponFnfView({ result, items: cart.invoiceItems, appliedCoupon: cart.appliedCoupon })
		expect(view.override).toBeNull()
		expect(view.result.appliedCount).toBe(1)
		expect(view.result.caps.fnf_applied_total).toBe(30)
		expect(view.result.caps.monthly_remaining_after).toBe(1820)
		const text = buildFnfCartMessages({ result: view.result, formatAmount: (v) => v.toFixed(2) }).map((m) => m.text).join(" | ")
		expect(text).toContain("30 1 30.00") // the spec's __ appends the args: 30%, 1 item, 30.00
		expect(text).toContain("30.00")
		expect(text).toContain("1820.00")
	})

	it("D-15: a line coupon on a line without F&F leaves the F&F view alone", () => {
		applyCoupon([lineUpdate(0, "A", 20)])
		const view = lineCouponFnfView({ result: fnfResult, items: cart.invoiceItems, appliedCoupon: cart.appliedCoupon })
		expect(view).toEqual({ override: null, result: fnfResult })
	})

	it("removing_coupon_restores_fnf", () => {
		// The server lets a 40% coupon replace F&F 30% on B
		applyCoupon([lineUpdate(0, "A", 40), lineUpdate(1, "B", 40)])
		const [a, b] = cart.invoiceItems
		expect(isFnfLine(b)).toBe(false)
		expect(b.discount_source).toBe("coupon")
		expect(lineDiscount(cart)).toBeCloseTo(80, 2)

		cart.removeDiscountFromCart()
		expect(a.discount_percentage).toBe(0)
		expect(a.coupon_code).toBeFalsy()
		expect(isFnfLine(b)).toBe(true)
		expect(b.discount_percentage).toBe(30)
		expect(lineDiscount(cart)).toBeCloseTo(30, 2)
	})

	it("a Sales Order drops the F&F kept under a coupon line, so removing the coupon does not bring it back", () => {
		applyCoupon([lineUpdate(0, "A", 40), lineUpdate(1, "B", 40)])
		cart.setTargetDoctype("Sales Order")
		cart.removeDiscountFromCart()
		const [a, b] = cart.invoiceItems
		expect(isFnfLine(b)).toBe(false)
		expect(b.discount_percentage).toBe(0)
		expect(a.discount_percentage).toBe(0)
	})

	it("a customer without F&F drops the F&F kept under a coupon line", async () => {
		applyCoupon([lineUpdate(0, "A", 40), lineUpdate(1, "B", 40)])
		cart.fnfEligibility = { eligible: false, customer: "CUST-2" }
		await cart.evaluateFriendsAndFamilyOnly({}, null, 0)
		cart.removeDiscountFromCart()
		expect(cart.invoiceItems[1].discount_percentage).toBe(0)
		expect(isFnfLine(cart.invoiceItems[1])).toBe(false)
	})
})
