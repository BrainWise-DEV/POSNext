/**
 * Client report 2026-11-18 (Task 8q): an F&F customer with a Buy X Get Y item.
 * Qty 1 has F&F, qty 2 has BXGY (F&F blocked on the line), and back at qty 1 F&F
 * must come back with no free row. The server answers are the real ones from
 * nexus.local (fixtures-ff-bxgy-qty-1-2-1.json); the F&F-only answer depends on
 * the request, as on the server: a line still tagged with the BXGY rule is blocked.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
	return { requests: [] }
})

const fixture = (await import("./fixtures-ff-bxgy-qty-1-2-1.json")).default
const RULE = fixture.rule
const ITEM = fixture.apply_offers_qty2.items[0].item_code
const CUSTOMER = fixture.eligibility.customer

const clone = (value) => JSON.parse(JSON.stringify(value))
const ruleNames = (value) =>
	(Array.isArray(value) ? value : String(value || "").split(",")).map((s) => s.trim()).filter(Boolean)

function applyOffersAnswer({ invoice_data }) {
	const paid = invoice_data.items.filter((i) => !i.is_free_item)
	const qty = paid.reduce((sum, i) => sum + Number(i.qty), 0)
	return clone(qty >= 2 ? fixture.apply_offers_qty2 : fixture.apply_offers_qty1)
}

function fnfOnlyAnswer({ items }) {
	expect(items.filter((i) => !i.is_free_item).map((i) => Number(i.qty))).toEqual([1])
	const tagged = items.some((i) => ruleNames(i.pricing_rules).includes(RULE))
	return clone(tagged ? fixture.fnf_only_qty1_bxgy_tagged : fixture.fnf_only_qty1)
}

vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: ({ url } = {}) => ({
		submit: vi.fn(async (params) => {
			if (!String(url).includes("apply_offers")) return {}
			server.requests.push({ method: "apply_offers", params: clone(params) })
			return applyOffersAnswer(params)
		}),
		reload: vi.fn(),
		fetch: vi.fn(),
	}),
}))
vi.mock("@/utils/apiWrapper", () => ({
	call: vi.fn(async (method, params) => {
		if (method.includes("check_friends_and_family_eligibility")) return clone(fixture.eligibility)
		if (method.includes("apply_friends_and_family_discount")) {
			server.requests.push({ method: "fnf_only", params: clone(params) })
			return fnfOnlyAnswer(params)
		}
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
vi.mock("@/utils/offerStrategies", async (importOriginal) => ({
	...(await importOriginal()),
	loadOfferStrategyPlugins: async () => {},
}))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }))
vi.mock("@/utils/offline/db", () => ({
	getOneTimeRedemptions: async () => [],
	setOneTimeRedemptions: async () => {},
	addOneTimeRedemptions: async () => {},
}))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("../posCart")
const { usePOSOffersStore } = await import("../posOffers")
const { isFnfLine } = await import("@/utils/friendsAndFamily")
const { offlineState } = await import("@/utils/offline/offlineState")

// The BXGY offer as get_offers returns it (posnext_promotions api/offers.py Offer.to_dict).
const BXGY_OFFER = {
	name: RULE,
	title: "Buy 2 Get 1",
	description: "",
	apply_on: "Item Code",
	offer: "Item Price",
	auto: 1,
	coupon_based: 0,
	min_qty: 2,
	max_qty: 0,
	min_amt: 0,
	max_amt: 0,
	discount_type: "Discount Percentage",
	rate: 0,
	discount_amount: 0,
	discount_percentage: 0,
	apply_discount_on_price: null,
	min_or_max_discount_qty_limit: 0,
	valid_from: null,
	valid_upto: null,
	source: "Promotional Scheme",
	promotional_scheme: "B2G1",
	promotional_scheme_id: "B2G1",
	eligible_items: [ITEM],
	eligible_item_groups: [],
	eligible_brands: [],
	free_item: ITEM,
	free_qty: 1,
	free_item_uom: "Nos",
	same_item: 1,
	is_recursive: 0,
}

const paidLine = (cart) => cart.invoiceItems.find((i) => !i.is_free_item)
const freeRows = (cart) => cart.invoiceItems.filter((i) => i.is_free_item)

async function settle(cart, seen) {
	await vi.waitFor(
		() => {
			expect(server.requests.length).toBeGreaterThan(seen)
			expect(cart.offerProcessingState.isProcessing).toBe(false)
		},
		{ timeout: 3000, interval: 20 }
	)
	// Let the post-flush watcher's debounce run out (it finds the hash unchanged).
	await new Promise((resolve) => setTimeout(resolve, 150))
	await vi.waitFor(() => expect(cart.offerProcessingState.isProcessing).toBe(false))
}

describe("F&F comes back when a BXGY line drops below its minimum (qty 1 → 2 → 1)", () => {
	let cart
	beforeEach(() => {
		server.requests = []
		vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(false)
		setActivePinia(createPinia())
		usePOSOffersStore().setAvailableOffers([BXGY_OFFER])
		cart = usePOSCartStore()
		cart.posProfile = "_PNXT_TEST_POS_PROFILE__Test Company"
		cart.customer = CUSTOMER
	})

	it("qty 1 has F&F, qty 2 has BXGY and no F&F, qty 1 has F&F again and no free row", async () => {
		cart.addItem({
			item_code: ITEM,
			item_name: "ITEM_A",
			rate: 50,
			price_list_rate: 50,
			uom: "Nos",
			stock_uom: "Nos",
			conversion_factor: 1,
		})
		await settle(cart, 0)
		expect(isFnfLine(paidLine(cart))).toBe(true)
		expect(paidLine(cart).amount).toBeCloseTo(35, 2)
		expect(freeRows(cart)).toHaveLength(0)

		let seen = server.requests.length
		cart.updateItemQuantity(ITEM, 2)
		await settle(cart, seen)
		expect(server.requests.at(-1).method).toBe("apply_offers")
		expect(isFnfLine(paidLine(cart))).toBe(false)
		expect(ruleNames(paidLine(cart).pricing_rules)).toEqual([RULE])
		expect(paidLine(cart).amount).toBeCloseTo(100, 2)
		expect(freeRows(cart)).toHaveLength(1)
		expect(cart.appliedOffers.map((o) => o.code)).toEqual([RULE])

		seen = server.requests.length
		cart.updateItemQuantity(ITEM, 1)
		await settle(cart, seen)
		const last = server.requests.at(-1)
		const sent = last.method === "fnf_only" ? last.params.items : last.params.invoice_data.items
		// The line no longer qualifies for BXGY: it must not reach the server tagged with it.
		expect(sent.flatMap((i) => ruleNames(i.pricing_rules))).not.toContain(RULE)
		expect(isFnfLine(paidLine(cart))).toBe(true)
		expect(paidLine(cart).amount).toBeCloseTo(35, 2)
		expect(ruleNames(paidLine(cart).pricing_rules)).toEqual([])
		expect(freeRows(cart)).toHaveLength(0)
		expect(cart.appliedOffers).toHaveLength(0)
	})

	it("removing the BXGY offer at qty 2, then qty 1, brings F&F back", async () => {
		cart.addItem({
			item_code: ITEM,
			item_name: "ITEM_A",
			rate: 50,
			price_list_rate: 50,
			uom: "Nos",
			stock_uom: "Nos",
			conversion_factor: 1,
		})
		await settle(cart, 0)
		let seen = server.requests.length
		cart.updateItemQuantity(ITEM, 2)
		await settle(cart, seen)
		expect(cart.appliedOffers.map((o) => o.code)).toEqual([RULE])

		await cart.removeOffer(RULE)
		seen = server.requests.length
		cart.updateItemQuantity(ITEM, 1)
		await settle(cart, seen)
		const last = server.requests.at(-1)
		const sent = last.method === "fnf_only" ? last.params.items : last.params.invoice_data.items
		expect(sent.flatMap((i) => ruleNames(i.pricing_rules))).not.toContain(RULE)
		expect(isFnfLine(paidLine(cart))).toBe(true)
		expect(paidLine(cart).amount).toBeCloseTo(35, 2)
		expect(freeRows(cart)).toHaveLength(0)
	})
})
