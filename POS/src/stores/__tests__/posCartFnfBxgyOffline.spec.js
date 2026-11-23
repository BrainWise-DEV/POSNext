/**
 * J1: "Allow Free Gift with F&F" off. A line priced online with F&F (qty 1) goes
 * offline and the qty rises past the BXGY minimum: the offline BXGY gift must not sit
 * next to the F&F price. You get F&F or the free unit, never both (task 8s, Q1).
 * Server answers: fixtures-ff-bxgy-qty-1-2-1.json (box off in its eligibility program).
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? s.replace(/\{(\d+)\}/g, (_, i) => args[i]) : s)
	return { requests: [] }
})

const fixture = (await import("./fixtures-ff-bxgy-qty-1-2-1.json")).default
const RULE = fixture.rule
const ITEM = fixture.apply_offers_qty2.items[0].item_code
const CUSTOMER = fixture.eligibility.customer
const clone = (value) => JSON.parse(JSON.stringify(value))

vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: ({ url } = {}) => ({
		submit: vi.fn(async (params) => {
			if (!String(url).includes("apply_offers")) return {}
			server.requests.push({ method: "apply_offers", params: clone(params) })
			return clone(fixture.apply_offers_qty2)
		}),
		reload: vi.fn(),
		fetch: vi.fn(),
	}),
}))
vi.mock("@/utils/apiWrapper", () => ({
	call: vi.fn(async (method, params) => {
		if (method.includes("check_friends_and_family_eligibility")) return clone(server.eligibility)
		if (method.includes("apply_friends_and_family_discount")) {
			server.requests.push({ method: "fnf_only", params: clone(params) })
			const answer = clone(fixture.fnf_only_qty1)
			answer.caps = { ...answer.caps, active: true, monthly_remaining: 287.5, monthly_remaining_after: 272.5 }
			return answer
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
const { buildFnfCartMessages, isFnfLine, lineCouponFnfView } = await import("@/utils/friendsAndFamily")
const { offlineState } = await import("@/utils/offline/offlineState")

const BXGY_OFFER = {
	name: RULE,
	title: "Buy 2 Get 1",
	apply_on: "Item Code",
	offer: "Give Product",
	auto: 1,
	coupon_based: 0,
	min_qty: 2,
	max_qty: 0,
	min_amt: 0,
	max_amt: 0,
	discount_type: "Discount Percentage",
	eligible_items: [ITEM],
	eligible_item_groups: [],
	eligible_brands: [],
	free_item: ITEM,
	free_qty: 1,
	free_item_uom: "Nos",
	same_item: 1,
	is_recursive: 0,
}

// A Price "buy one" rule: 100% off one unit of a Min rule (the server's Buy X Get Y too).
const BUY_ONE_OFFER = {
	...BXGY_OFFER,
	name: "_PNXT_J1_BUY1",
	title: "Buy one",
	offer: "Item Price",
	discount_type: "Discount Percentage",
	discount_percentage: 100,
	apply_discount_on_price: "Min",
	min_or_max_discount_qty_limit: 1,
	free_item: null,
	free_qty: 0,
	same_item: 0,
}

const paidLines = (cart) => cart.invoiceItems.filter((i) => !i.is_free_item)
const paidLine = (cart, uom = "Nos") => paidLines(cart).find((i) => i.uom === uom)
const freeRows = (cart) => cart.invoiceItems.filter((i) => i.is_free_item)
const ITEM_ROW = { item_code: ITEM, item_name: "ITEM_A", rate: 50, price_list_rate: 50, uom: "Nos", stock_uom: "Nos", conversion_factor: 1 }

/** What the cart banner says (InvoiceCart's fnfCartMessages, without a coupon). */
function banner(cart) {
	const { result } = lineCouponFnfView({ result: cart.fnfResult, items: cart.invoiceItems })
	return buildFnfCartMessages({ result, eligibility: cart.fnfEligibility, formatAmount: (v) => Number(v).toFixed(2) })
		.map((m) => m.text)
		.join(" | ")
}

/** The cart priced the cart it now holds: the pass for `qty` has stamped its hash and is idle. */
async function pricedAt(cart, qty) {
	await vi.waitFor(
		() => {
			expect(cart.offerProcessingState.lastCartHash).toContain(`${ITEM}:${qty}:`)
			expect(cart.offerProcessingState.isProcessing).toBe(false)
		},
		{ timeout: 3000, interval: 10 }
	)
}

describe("J1 offline: F&F or the Buy X Get Y free unit, never both", () => {
	let cart
	let offline

	function freshCart(offers) {
		setActivePinia(createPinia())
		usePOSOffersStore().setAvailableOffers(offers)
		cart = usePOSCartStore()
		cart.posProfile = "_PNXT_TEST_POS_PROFILE__Test Company"
		cart.customer = CUSTOMER
	}

	beforeEach(() => {
		server.requests = []
		offline = false
		vi.spyOn(offlineState, "isOffline", "get").mockImplementation(() => offline)
		freshCart([BXGY_OFFER])
	})

	/** Online F&F at qty 1 (box `allow`), then offline. */
	async function fnfOnlineThenOffline(allow) {
		server.eligibility = clone(fixture.eligibility)
		server.eligibility.program.allow_free_gift_with_ff = allow
		cart.addItem({ ...ITEM_ROW })
		await pricedAt(cart, 1)
		expect(isFnfLine(paidLine(cart))).toBe(true)
		expect(banner(cart)).toContain("applied to 1 item(s) — saving 15.00")
		expect(banner(cart)).toContain("287.50 left, 272.50 after this order")
		offline = true
	}

	it("qty 1 → 3 offline: box off drops F&F beside the free unit, line and banner agree; box on keeps both", async () => {
		await fnfOnlineThenOffline(false)
		cart.updateItemQuantity(ITEM, 3)
		await pricedAt(cart, 3)
		expect(freeRows(cart)).toHaveLength(1)
		expect(isFnfLine(paidLine(cart))).toBe(false)
		expect(paidLine(cart).amount).toBeCloseTo(150, 2)
		expect(paidLine(cart).fnf_reason).toBe("scheme_not_eligible")
		// The summary no longer claims the F&F saving the line lost (review I-1).
		expect(cart.fnfResult.appliedCount).toBe(0)
		expect(banner(cart)).not.toContain("applied to")
		expect(banner(cart)).toContain("Monthly Friends & Family balance: 287.50 left")
		expect(banner(cart)).not.toContain("after this order")

		// Control, a fresh cart: with the box on the server gives both, and so does offline.
		offline = false
		freshCart([BXGY_OFFER])
		await fnfOnlineThenOffline(true)
		cart.updateItemQuantity(ITEM, 3)
		await pricedAt(cart, 3)
		expect(freeRows(cart)).toHaveLength(1)
		expect(isFnfLine(paidLine(cart))).toBe(true)
		expect(banner(cart)).toContain("applied to 1 item(s)")
	})

	it("no eligibility answer (a draft loaded offline): the box reads as off, the Settings default", async () => {
		await fnfOnlineThenOffline(true)
		// As a draft restored offline: F&F lines, but nothing asked about the customer yet.
		cart.fnfEligibility = null
		cart.updateItemQuantity(ITEM, 3)
		await pricedAt(cart, 3)
		expect(freeRows(cart)).toHaveLength(1)
		expect(isFnfLine(paidLine(cart))).toBe(false)
	})

	it("only the line the gift belongs to (same item and unit) loses F&F", async () => {
		await fnfOnlineThenOffline(false)
		// A second F&F line of the same item in another unit, priced online with F&F too.
		const nos = paidLine(cart)
		cart.invoiceItems.push({ ...clone(nos), uom: "Box", conversion_factor: 6, quantity: 1 })
		cart.updateItemQuantity(ITEM, 3, "Nos")
		await pricedAt(cart, 3)
		const gifts = freeRows(cart)
		expect(gifts).toHaveLength(1)
		expect(gifts[0].uom).toBe("Nos")
		expect(isFnfLine(paidLine(cart, "Nos"))).toBe(false)
		expect(isFnfLine(paidLine(cart, "Box"))).toBe(true)
		expect(cart.fnfResult.appliedCount).toBe(1)
	})

	it("a Price buy-one offer offline does not land on an F&F line", async () => {
		freshCart([BUY_ONE_OFFER])
		await fnfOnlineThenOffline(false)
		cart.updateItemQuantity(ITEM, 4)
		await pricedAt(cart, 4)
		const line = paidLine(cart)
		// It keeps the F&F price the server gave it; it never also takes 100% off.
		expect(isFnfLine(line)).toBe(true)
		expect(Number(line.discount_percentage)).toBeCloseTo(30, 2)
		expect(line.pricing_rules || []).not.toContain(BUY_ONE_OFFER.name)
	})
})
