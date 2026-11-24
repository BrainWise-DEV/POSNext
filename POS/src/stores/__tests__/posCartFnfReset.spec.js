/**
 * Regression tests on develop: Friends & Family discount must come back when a
 * promotion stops applying (qty decrease, orphaned applied_pricing_rules,
 * reapplyOffer, or removeOffer on a Transaction header offer).
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const RULE = "PRLE-BXGY-COSRX"
const ITEM = "COSRX-EYE-CREAM-25ML"
const CUSTOMER = "FNF-TEST-CUSTOMER"

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
	return { requests: [], omitAppliedRules: false, customApplyOffers: null }
})

const clone = (v) => JSON.parse(JSON.stringify(v))
const ruleNames = (value) =>
	(Array.isArray(value) ? value : String(value || "").split(",")).map((s) => s.trim()).filter(Boolean)

const ELIGIBILITY = {
	customer: CUSTOMER,
	eligible: true,
	reason: "email_verified",
	message: "Customer is eligible for Friends & Family",
	program_active: true,
	discount_percentage: 30,
	program: { active: true, discount_percentage: 30, discount_scope: "Entire Cart" },
}

function makeFnfBlock(applies, rate = 18900, discountAmount = 8100, reason = "applied") {
	return {
		eligible: true,
		discount_percentage: 30,
		applied_count: applies ? 1 : 0,
		message: "Customer is eligible for Friends & Family",
		reason: "email_verified",
		items: [
			{
				item_code: ITEM,
				idx: 0,
				applies,
				discount_percentage: applies ? 30 : 0,
				discount_amount: applies ? discountAmount : 0,
				rate: applies ? rate : 27000,
				reason,
			},
		],
	}
}

function applyOffersAnswer({ invoice_data, selected_offers }) {
	if (server.customApplyOffers) {
		return server.customApplyOffers({ invoice_data, selected_offers })
	}
	const paid = invoice_data.items.filter((i) => !i.is_free_item)
	const qty = paid.reduce((sum, i) => sum + Number(i.qty), 0)
	if (qty >= 2) {
		return {
			items: [
				{
					item_code: ITEM,
					qty,
					price_list_rate: 27000,
					rate: 27000,
					discount_percentage: 0,
					discount_amount: 0,
					pricing_rules: [RULE],
					discount_source: "gwp",
					gwp_free_qty: 1,
					is_already_discounted: 1,
				},
			],
			free_items: [
				{
					item_code: ITEM,
					item_name: "Cosrx Advanced Snail Peptide Eye Cream - 25ml",
					qty: 1,
					uom: "Nos",
					rate: 0,
					price_list_rate: 0,
					is_free_item: 1,
					pricing_rules: RULE,
					same_item: 1,
				},
			],
			applied_pricing_rules: server.omitAppliedRules ? [] : [RULE],
			discount_amount: 0,
			apply_discount_on: "Grand Total",
			friends_and_family: makeFnfBlock(false, 27000, 0, "scheme_not_eligible"),
		}
	}
	return {
		items: [
			{
				item_code: ITEM,
				qty: 1,
				price_list_rate: 27000,
				rate: 18900,
				discount_percentage: 30,
				discount_amount: 8100,
				pricing_rules: [],
				discount_source: "friends_and_family",
				is_already_discounted: 1,
			},
		],
		free_items: [],
		applied_pricing_rules: [],
		discount_amount: 0,
		apply_discount_on: "Grand Total",
		friends_and_family: makeFnfBlock(true),
	}
}

function fnfOnlyAnswer({ items }) {
	const hasStaleRule = items.some((i) => ruleNames(i.pricing_rules).includes(RULE))
	if (hasStaleRule) {
		return makeFnfBlock(false, 27000, 0, "scheme_not_eligible")
	}
	return makeFnfBlock(true)
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
		if (method.includes("check_friends_and_family_eligibility")) return clone(ELIGIBILITY)
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

const BXGY_OFFER = {
	name: RULE,
	title: "Buy 2 Get 1",
	apply_on: "Item Code",
	offer: "Item Price",
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

const COSRX_ITEM = {
	item_code: ITEM,
	item_name: "Cosrx Advanced Snail Peptide Eye Cream - 25ml",
	rate: 27000,
	price_list_rate: 27000,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
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
	await new Promise((resolve) => setTimeout(resolve, 150))
	await vi.waitFor(() => expect(cart.offerProcessingState.isProcessing).toBe(false))
}

describe("F&F discount restoration after promotion applies and qty decreases (develop)", () => {
	let cart
	beforeEach(() => {
		server.requests = []
		server.omitAppliedRules = false
		server.customApplyOffers = null
		vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(false)
		setActivePinia(createPinia())
		usePOSOffersStore().setAvailableOffers([BXGY_OFFER])
		cart = usePOSCartStore()
		cart.posProfile = "_PNXT_TEST_POS_PROFILE"
		cart.customer = CUSTOMER
	})

	it("qty 1 has F&F, qty 2 applies BXGY, qty 1 restores F&F and clears free row", async () => {
		cart.addItem(COSRX_ITEM)
		await settle(cart, 0)
		expect(isFnfLine(paidLine(cart))).toBe(true)
		expect(paidLine(cart).amount).toBeCloseTo(18900, 2)

		let seen = server.requests.length
		cart.updateItemQuantity(ITEM, 2)
		await settle(cart, seen)
		expect(isFnfLine(paidLine(cart))).toBe(false)
		expect(freeRows(cart)).toHaveLength(1)

		seen = server.requests.length
		cart.updateItemQuantity(ITEM, 1)
		await settle(cart, seen)
		expect(isFnfLine(paidLine(cart))).toBe(true)
		expect(paidLine(cart).amount).toBeCloseTo(18900, 2)
		expect(ruleNames(paidLine(cart).pricing_rules)).toEqual([])
		expect(freeRows(cart)).toHaveLength(0)
	})

	it("cleans orphaned promotion tags when applied_pricing_rules was omitted", async () => {
		server.omitAppliedRules = true
		cart.addItem(COSRX_ITEM)
		await settle(cart, 0)
		expect(isFnfLine(paidLine(cart))).toBe(true)

		let seen = server.requests.length
		cart.updateItemQuantity(ITEM, 2)
		await settle(cart, seen)
		expect(cart.appliedOffers).toHaveLength(0)
		expect(ruleNames(paidLine(cart).pricing_rules)).toEqual([RULE])
		expect(freeRows(cart)).toHaveLength(1)
		expect(isFnfLine(paidLine(cart))).toBe(false)

		seen = server.requests.length
		cart.updateItemQuantity(ITEM, 1)
		await settle(cart, seen)
		const last = server.requests.at(-1)
		expect(last.method).toBe("fnf_only")
		expect(last.params.items.flatMap((i) => ruleNames(i.pricing_rules))).not.toContain(RULE)
		expect(isFnfLine(paidLine(cart))).toBe(true)
		expect(paidLine(cart).amount).toBeCloseTo(18900, 2)
		expect(paidLine(cart).gwp_free_qty).toBe(0)
		expect(freeRows(cart)).toHaveLength(0)
	})

	it("reapplyOffer clearing the last offer restores F&F", async () => {
		cart.addItem(COSRX_ITEM)
		await settle(cart, 0)
		let seen = server.requests.length
		cart.updateItemQuantity(ITEM, 2)
		await settle(cart, seen)
		expect(cart.appliedOffers.map((o) => o.code)).toEqual([RULE])

		cart.updateItemQuantity(ITEM, 1)
		cart.cancelPendingOfferProcessing()
		seen = server.requests.length
		const removed = await cart.reapplyOffer({})
		expect(removed).toBe(true)
		expect(server.requests.length).toBeGreaterThan(seen)
		expect(server.requests.at(-1).method).toBe("fnf_only")
		expect(isFnfLine(paidLine(cart))).toBe(true)
		expect(paidLine(cart).amount).toBeCloseTo(18900, 2)
		expect(freeRows(cart)).toHaveLength(0)
	})

	it("removeOffer on a Transaction header offer restores F&F without a qty change", async () => {
		const ORDER_OFFER = {
			...BXGY_OFFER,
			name: "ORDER_OFFER",
			title: "Order 10000 Off",
			apply_on: "Transaction",
			offer: "Grand Total",
			min_qty: 0,
			min_amt: 20000,
			discount_type: "Discount Amount",
			discount_amount: 10000,
			eligible_items: [],
			free_item: null,
			free_qty: 0,
			same_item: 0,
		}
		usePOSOffersStore().setAvailableOffers([ORDER_OFFER])
		server.customApplyOffers = ({ invoice_data, selected_offers }) => {
			const hasOrder = (selected_offers || []).includes("ORDER_OFFER")
			return {
				items: invoice_data.items.map((i) => ({
					...i,
					discount_percentage: 0,
					discount_amount: 0,
					pricing_rules: [],
					is_already_discounted: 0,
					discount_source: "",
				})),
				free_items: [],
				applied_pricing_rules: hasOrder ? ["ORDER_OFFER"] : [],
				discount_amount: hasOrder ? 10000 : 0,
				apply_discount_on: hasOrder ? "Grand Total" : null,
				friends_and_family: hasOrder
					? makeFnfBlock(false, 27000, 0, "order_discount_better")
					: makeFnfBlock(true),
			}
		}

		cart.addItem(COSRX_ITEM)
		await settle(cart, 0)
		expect(cart.appliedOffers.map((o) => o.code)).toEqual(["ORDER_OFFER"])
		expect(cart.additionalDiscount).toBe(10000)
		expect(isFnfLine(paidLine(cart))).toBe(false)

		const seen = server.requests.length
		await cart.removeOffer("ORDER_OFFER", {})
		await settle(cart, seen)
		expect(cart.appliedOffers).toHaveLength(0)
		expect(cart.additionalDiscount).toBe(0)
		expect(server.requests.at(-1).method).toBe("fnf_only")
		expect(isFnfLine(paidLine(cart))).toBe(true)
		expect(paidLine(cart).amount).toBeCloseTo(18900, 2)
	})
})
