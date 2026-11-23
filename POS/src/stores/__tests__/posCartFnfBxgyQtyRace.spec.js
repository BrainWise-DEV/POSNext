/**
 * J1 (user video 2026-11-23): an F&F customer with a Buy X Get Y item, "Allow Free Gift
 * with F&F" off. The qty changes while a pricing answer is still on its way. The answer
 * was asked for the old qty: it must not stand for the new one. The cart asks again, so
 * the line never keeps F&F at a qty where BXGY applies.
 * Server answers: fixtures-ff-bxgy-qty-1-2-1.json (real answers, see posCartFnfBxgyQty.spec.js).
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
	return { requests: [], hold: null }
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
	const tagged = items.some((i) => ruleNames(i.pricing_rules).includes(RULE))
	return clone(tagged ? fixture.fnf_only_qty1_bxgy_tagged : fixture.fnf_only_qty1)
}

vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: ({ url } = {}) => ({
		submit: vi.fn(async (params) => {
			if (!String(url).includes("apply_offers")) return {}
			server.requests.push({ method: "apply_offers", params: clone(params) })
			const answer = applyOffersAnswer(params)
			if (!server.hold) return answer
			return new Promise((resolve) => {
				server.hold.release = () => resolve(answer)
			})
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
			const answer = fnfOnlyAnswer(params)
			if (!server.hold) return answer
			// Held: the test decides when this answer arrives.
			return new Promise((resolve) => {
				server.hold.release = () => resolve(answer)
			})
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
	offer: "Give Product",
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

const sentQty = (request) =>
	(request.method === "fnf_only" ? request.params.items : request.params.invoice_data.items)
		.filter((i) => !i.is_free_item)
		.reduce((sum, i) => sum + Number(i.qty), 0)

const ITEM_ROW = {
	item_code: ITEM,
	item_name: "ITEM_A",
	rate: 50,
	price_list_rate: 50,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
}

describe("J1: an answer for the old qty does not stand for the new qty", () => {
	let cart
	beforeEach(() => {
		server.requests = []
		server.hold = null
		vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(false)
		setActivePinia(createPinia())
		usePOSOffersStore().setAvailableOffers([BXGY_OFFER])
		cart = usePOSCartStore()
		cart.posProfile = "_PNXT_TEST_POS_PROFILE__Test Company"
		cart.customer = CUSTOMER
	})

	it("qty 1 → 2 while the qty-1 F&F answer is out: the qty-2 cart is priced, BXGY and no F&F", async () => {
		server.hold = {}
		cart.addItem(ITEM_ROW)
		await vi.waitFor(() => expect(server.hold.release).toBeTypeOf("function"), { timeout: 3000, interval: 5 })
		const held = server.hold
		server.hold = null
		expect(server.requests.at(-1).method).toBe("fnf_only")
		expect(sentQty(server.requests.at(-1))).toBe(1)

		// The cashier presses + before the qty-1 answer is back; the answer lands
		// before the cart's own debounce runs.
		cart.updateItemQuantity(ITEM, 2)
		held.release()
		await settle(cart, 1)
		await new Promise((resolve) => setTimeout(resolve, 300))
		await vi.waitFor(() => expect(cart.offerProcessingState.isProcessing).toBe(false))

		expect(server.requests.map((r) => [r.method, sentQty(r)])).toContainEqual(["apply_offers", 2])
		expect(isFnfLine(paidLine(cart))).toBe(false)
		expect(paidLine(cart).amount).toBeCloseTo(100, 2)
		expect(freeRows(cart)).toHaveLength(1)
	})

	it("qty 2 → 1 while the qty-2 BXGY answer is out: the qty-1 cart is priced, F&F and no free row", async () => {
		cart.addItem(ITEM_ROW)
		await settle(cart, 0)
		const seen = server.requests.length
		server.hold = {}
		cart.updateItemQuantity(ITEM, 2)
		await vi.waitFor(() => expect(server.hold.release).toBeTypeOf("function"), { timeout: 3000, interval: 5 })
		const held = server.hold
		server.hold = null
		expect(sentQty(server.requests.at(-1))).toBe(2)

		cart.updateItemQuantity(ITEM, 1)
		held.release()
		await new Promise((resolve) => setTimeout(resolve, 400))
		await vi.waitFor(() => expect(cart.offerProcessingState.isProcessing).toBe(false))
		await new Promise((resolve) => setTimeout(resolve, 200))

		// The qty-2 answer (BXGY, a free row) never lands on the qty-1 cart.
		expect(ruleNames(paidLine(cart).pricing_rules)).not.toContain(RULE)
		expect(cart.appliedOffers).toHaveLength(0)
		expect(isFnfLine(paidLine(cart))).toBe(true)
		expect(paidLine(cart).amount).toBeCloseTo(35, 2)
		expect(freeRows(cart)).toHaveLength(0)
	})
	it("qty 2 → 1 while POSSale's reapplyOffer answer for qty 2 is out: it never lands on qty 1", async () => {
		cart.addItem(ITEM_ROW)
		await settle(cart, 0)
		let seen = server.requests.length
		cart.updateItemQuantity(ITEM, 2)
		await settle(cart, seen)
		expect(freeRows(cart)).toHaveLength(1)

		// A second applied offer the cart no longer meets, so reapplyOffer re-prices the
		// rest (as POSSale's watcher does 500 ms after a change).
		const CART_OFFER = {
			...BXGY_OFFER,
			name: "_PNXT_J1_CART",
			apply_on: "Transaction",
			offer: "Item Price",
			min_qty: 0,
			min_amt: 1000000,
			eligible_items: [],
			same_item: 0,
			free_item: null,
		}
		cart.appliedOffers.push({ name: CART_OFFER.name, code: CART_OFFER.name, offer: CART_OFFER, source: "auto", applied: true, rules: [CART_OFFER.name] })
		server.hold = {}
		const reapplied = cart.reapplyOffer({ name: cart.posProfile, company: "_Test Company", currency: "INR", selling_price_list: "Standard Selling" })
		await vi.waitFor(() => expect(server.hold.release).toBeTypeOf("function"), { timeout: 3000, interval: 5 })
		const held = server.hold
		server.hold = null
		expect(server.requests.at(-1).method).toBe("apply_offers")
		expect(sentQty(server.requests.at(-1))).toBe(2)

		// The cashier presses − meanwhile; the cart prices qty 1 (F&F, no gift) first.
		seen = server.requests.length
		cart.updateItemQuantity(ITEM, 1)
		await settle(cart, seen)
		expect(isFnfLine(paidLine(cart))).toBe(true)

		held.release()
		await reapplied
		await vi.waitFor(() => expect(cart.offerProcessingState.isProcessing).toBe(false))
		await new Promise((resolve) => setTimeout(resolve, 200))
		await vi.waitFor(() => expect(cart.offerProcessingState.isProcessing).toBe(false))

		expect(freeRows(cart)).toHaveLength(0)
		expect(ruleNames(paidLine(cart).pricing_rules)).not.toContain(RULE)
		expect(isFnfLine(paidLine(cart))).toBe(true)
		expect(paidLine(cart).amount).toBeCloseTo(35, 2)
		expect(cart.fnfResult?.appliedCount).toBe(1)
	})
})
