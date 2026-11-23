/**
 * POS Profile ignore_pricing_rule turns pricing rules off, not F&F: the server still
 * prices F&F on save, so the cart shows it too (UI test D-R3-11).
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"
import fixture from "./fixtures-ff-bxgy-qty-1-2-1.json"

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
	return { requests: [] }
})
const shift = vi.hoisted(() => ({ currentProfile: { name: "POS-1", ignore_pricing_rule: 1 } }))
const clone = (value) => JSON.parse(JSON.stringify(value))
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: ({ url } = {}) => ({
		submit: vi.fn(async () => {
			server.requests.push({ method: String(url) })
			return {}
		}),
		reload: vi.fn(),
		fetch: vi.fn(),
	}),
}))
vi.mock("@/utils/apiWrapper", () => ({
	call: vi.fn(async (method, params) => {
		server.requests.push({ method, params: clone(params) })
		if (method.includes("check_friends_and_family_eligibility")) return clone(fixture.eligibility)
		if (method.includes("apply_friends_and_family_discount")) return clone(fixture.fnf_only_qty1)
		return []
	}),
}))
vi.mock("@/utils/promoApi", () => ({
	isPromotionsAppInstalled: () => true,
	promoApi: {
		applyOffers: () => "posnext_promotions.api.offers.apply_offers",
		applyFriendsAndFamilyDiscount: () =>
			"posnext_promotions.api.friends_and_family.apply_friends_and_family_discount",
		checkFriendsAndFamilyEligibility: () =>
			"posnext_promotions.api.friends_and_family.check_friends_and_family_eligibility",
		getCustomerOneTimeRedemptions: () => "posnext_promotions.api.offers.get_customer_one_time_redemptions",
		getOffers: () => "posnext_promotions.api.offers.get_offers",
		validateCoupon: () => "posnext_promotions.api.offers.validate_coupon",
	},
}))
vi.mock("@/stores/posShift", () => ({ usePOSShiftStore: () => shift }))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("../posCart")

const ITEM = {
	item_code: fixture.fnf_only_qty1.items[0].item_code,
	item_name: "A",
	rate: 50,
	price_list_rate: 50,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
}

describe("D-R3-11: F&F with pricing rules ignored", () => {
	let cart
	beforeEach(() => {
		server.requests.length = 0
		setActivePinia(createPinia())
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = { name: fixture.eligibility.customer }
	})

	it("the cart shows the F&F discount the server will save, and asks for no pricing rule", async () => {
		cart.addItem({ ...ITEM })
		cart.forceRefreshOffers()
		await vi.waitFor(() => expect(cart.invoiceItems[0].amount).toBe(35), { timeout: 3000 })
		expect(cart.invoiceItems[0].discount_amount).toBe(15)
		expect(cart.invoiceItems[0].discount_source).toBe("friends_and_family")
		const methods = server.requests.map((r) => r.method)
		expect(methods.some((m) => m.includes("apply_friends_and_family_discount"))).toBe(true)
		expect(methods.some((m) => m.includes("apply_offers") || m.includes("get_offers"))).toBe(false)
	})
})
