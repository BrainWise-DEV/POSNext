/**
 * The cart's customer saved again with a new email (verification cleared): the open
 * cart is re-priced, as a customer change re-prices it (UI test D-R3-07).
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"
import fixture from "./fixtures-ff-bxgy-qty-1-2-1.json"

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
	return { requests: [], eligible: true }
})
const shift = vi.hoisted(() => ({ currentProfile: { name: "POS-1", ignore_pricing_rule: 0 } }))
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
		if (method.includes("check_friends_and_family_eligibility"))
			return server.eligible
				? clone(fixture.eligibility)
				: { ...clone(fixture.eligibility), eligible: false, reason: "email_not_verified" }
		if (method.includes("apply_friends_and_family_discount"))
			return server.eligible
				? clone(fixture.fnf_only_qty1)
				: { ...clone(fixture.fnf_only_qty1), eligible: false, items: [] }
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
const CUSTOMER = fixture.eligibility.customer

describe("D-R3-07: the same customer saved with a new email", () => {
	let cart
	beforeEach(async () => {
		server.requests.length = 0
		server.eligible = true
		setActivePinia(createPinia())
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		await cart.setCustomer({ name: CUSTOMER, email_id: "a@fftest.example" })
		cart.addItem({ ...ITEM })
		await vi.waitFor(() => expect(cart.invoiceItems[0].amount).toBe(35), { timeout: 3000 })
	})

	it("drops the F&F price at once when the save clears the verification", async () => {
		server.eligible = false
		await cart.setCustomer({ name: CUSTOMER, email_id: "b@fftest.example" })
		await vi.waitFor(() => expect(cart.invoiceItems[0].amount).toBe(50), { timeout: 3000 })
		expect(cart.invoiceItems[0].discount_source).not.toBe("friends_and_family")
	})

	it("does not re-price when the save leaves the eligibility as it was", async () => {
		const before = server.requests.length
		await cart.setCustomer({ name: CUSTOMER, mobile_no: "0100" })
		await new Promise((resolve) => setTimeout(resolve, 800))
		const fnfCalls = server.requests
			.slice(before)
			.filter((r) => r.method.includes("apply_friends_and_family_discount"))
		expect(fnfCalls).toHaveLength(0)
	})
})
