/**
 * posnext_promotions K1: under Friends and Family Settings "Better of the two for the
 * whole cart" (the default), a coupon that beats F&F on the cart takes it whole. A
 * scoped coupon covers only some lines, so the cart must strip F&F from the others
 * too, or the invoice refuses the two mixed. Real cart store, real dialog.
 * @vitest-environment jsdom
 */
import { mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
	return { calc: {} }
})

vi.mock("frappe-ui", () => ({
	Button: { template: "<button><slot /></button>" },
	Dialog: { template: "<div><slot name='body-content' /><slot /></div>" },
	Input: { template: "<input />" },
	call: vi.fn(async (method) =>
		method === "calc"
			? server.calc
			: { valid: true, coupon: { coupon_code: "BRAND30", discount_type: "Amount", discount_amount: 30 } }
	),
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn() }),
}))
vi.mock("@/utils/promoApi", () => ({
	isPromotionsAppInstalled: () => true,
	promoOrPos: (a) => a,
	promoApi: new Proxy(
		{
			getActiveCoupons: () => "x",
			validateCoupon: () => "validate",
			calculateCouponDiscount: () => "calc",
			applyFriendsAndFamilyDiscount: () => "fnf",
		},
		{ get: (target, key) => target[key] || (() => String(key)) }
	),
}))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("@/stores/posCart")
const { stampFnfLine } = await import("@/utils/friendsAndFamily")
const { default: CouponDialog } = await import("../CouponDialog.vue")

const FNF = "friends_and_family"
const item = (code, price) => ({
	item_code: code,
	item_name: code,
	rate: price,
	price_list_rate: price,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
})

// A brand coupon covers B only. The reply is the server's: the coupon takes B, and under
// "whole cart" it holds the cart (replaces_friends_and_family_on_cart).
const reply = (wholeCart) => ({
	valid: true,
	granularity: "line",
	discount: 30,
	suppress_friends_and_family: true,
	replaces_friends_and_family_on_cart: wholeCart,
	line_updates: [
		{
			line_key: 1,
			item_code: "B",
			discount_percentage: 0,
			discount_amount: 30,
			rate: 70,
			amount: 70,
			coupon_code: "BRAND30",
			coupon_only_discount: 30,
		},
	],
})

describe("a whole-cart coupon strips F&F from the lines it does not cover", () => {
	let cart
	beforeEach(() => {
		setActivePinia(createPinia())
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = "CUST-1"
		cart.addItem(item("A", 50))
		cart.addItem(item("B", 100))
		for (const [line, off] of [
			[cart.invoiceItems[0], 15],
			[cart.invoiceItems[1], 30],
		]) {
			stampFnfLine(line, {
				discount_percentage: 30,
				discount_amount: off,
				rate: line.price_list_rate - off,
				applies: true,
			})
			cart.recalculateItem(line)
		}
		cart.fnfEligibility = { eligible: true, discountPercentage: 30 }
	})

	async function applyFromDialog(wholeCart) {
		server.calc = reply(wholeCart)
		const wrapper = mount(CouponDialog, {
			props: { modelValue: true, subtotal: 150, grandTotal: 150, customer: "CUST-1", company: "Nexus" },
			global: { mocks: { __: globalThis.__ } },
		})
		wrapper.vm.$.setupState.couponCode = "BRAND30"
		await wrapper.vm.$.setupState.applyCoupon()
		const [discount] = wrapper.emitted("discount-applied")[0]
		cart.applyDiscountToCart(discount) // what POSSale does with the event
		return discount
	}

	it("whole cart: no F&F on the uncovered line, and the payload carries none", async () => {
		const discount = await applyFromDialog(true)
		expect(discount.line_level).toBe(true)
		expect(discount.suppress_friends_and_family).toBe(true)
		const [a, b] = cart.invoiceItems
		expect(a.discount_source).not.toBe(FNF)
		expect(Number(a.discount_amount || 0)).toBe(0)
		expect(b.coupon_code).toBe("BRAND30")
		// The payload the invoice validates: A at list price with no F&F, B the coupon's.
		const [rowA, rowB] = cart.formatItemsForSubmission(cart.invoiceItems)
		expect(rowA.posnext_discount_source || "").not.toBe(FNF)
		expect(rowA.posnext_coupon_code).toBeNull()
		expect(rowA.rate).toBe(50)
		expect(Number(rowA.discount_amount || 0)).toBe(0)
		expect(rowB.posnext_coupon_code).toBe("BRAND30")
		expect(rowB.rate).toBe(70)
		expect(cart.fnfCouponOverride?.code).toBe("BRAND30")
	})

	it("per line: the uncovered line keeps its F&F", async () => {
		const discount = await applyFromDialog(false)
		expect(discount.suppress_friends_and_family).toBe(false)
		const [a, b] = cart.invoiceItems
		expect(a.discount_source).toBe(FNF)
		expect(b.coupon_code).toBe("BRAND30")
		const [rowA] = cart.formatItemsForSubmission(cart.invoiceItems)
		expect(rowA.rate).toBe(35)
		expect(cart.fnfCouponOverride).toBeNull()
	})
})
