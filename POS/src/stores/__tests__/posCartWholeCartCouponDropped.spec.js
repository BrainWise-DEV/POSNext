/**
 * K1 re-review R1-I1: a whole-cart coupon (it stripped F&F from every line) that the
 * line re-check drops must bring F&F back, or the customer pays without it.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? s.replace(/\{(\d+)\}/g, (_, i) => args[i]) : s)
	window.posnext_app_flags = { posnext_promotions: 1 }
	return { methods: [] }
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async (method) => {
		const name = String(method)
		server.methods.push(name)
		if (name.includes("validate_coupon")) return { valid: false, message: "No eligible items for this coupon" }
		if (name.includes("apply_friends_and_family")) {
			// F&F 30% on what is left of the cart: A, 50 -> 35.
			return {
				eligible: true,
				discount_percentage: 30,
				applied_count: 1,
				items: [{ idx: 0, item_code: "A", applies: true, discount_percentage: 30, discount_amount: 15, rate: 35 }],
			}
		}
		if (name.includes("check_friends_and_family_eligibility")) {
			return { eligible: true, discount_percentage: 30, customer: "CUST-1" }
		}
		if (name.includes("get_offers")) return []
		return {}
	}),
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn() }),
}))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("../posCart")
const { stampFnfLine } = await import("@/utils/friendsAndFamily")

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
// The coupon is scoped to B and held the whole cart: the dialog's discount for it.
const wholeCartCoupon = {
	name: "BRAND30",
	code: "BRAND30",
	line_level: true,
	suppress_friends_and_family: true,
	coupon: { coupon_code: "BRAND30", discount_type: "Amount", discount_amount: 30 },
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
}

describe("a whole-cart coupon dropped on re-check brings F&F back", () => {
	let cart
	beforeEach(() => {
		setActivePinia(createPinia())
		server.methods = []
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = "CUST-1"
		cart.addItem(item("A", 50))
		cart.addItem(item("B", 100))
		for (const [line, off] of [
			[cart.invoiceItems[0], 15],
			[cart.invoiceItems[1], 30],
		]) {
			stampFnfLine(line, { discount_percentage: 30, discount_amount: off, rate: line.price_list_rate - off, applies: true })
			cart.recalculateItem(line)
		}
		cart.fnfEligibility = { eligible: true, discountPercentage: 30 }
		cart.applyDiscountToCart(wholeCartCoupon)
	})

	it("the cashier removes B: the coupon goes and A is back at its F&F price", async () => {
		expect(cart.invoiceItems[0].discount_source).not.toBe(FNF)
		expect(cart.fnfCouponOverride?.code).toBe("BRAND30")

		cart.removeItem("B")
		await vi.waitFor(() => expect(server.methods.some((m) => m.includes("validate_coupon"))).toBe(true), {
			timeout: 3000,
		})
		await vi.waitFor(
			() => {
				expect(cart.appliedCoupon).toBeNull()
				expect(cart.fnfCouponOverride).toBeNull()
				expect(cart.invoiceItems[0].discount_source).toBe(FNF)
			},
			{ timeout: 3000 }
		)
		const [rowA] = cart.formatItemsForSubmission(cart.invoiceItems)
		expect(rowA.rate).toBe(35)
	})
})
