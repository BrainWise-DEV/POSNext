/**
 * G7: offline, a Min/Max Price rule is priced as the server prices it, never as a
 * flat % on every line in scope.
 *
 * Before G7 a "buy one" rule (Min, 100% off, one unit) on 6 × 50 rang up 0.00
 * offline: posnext_promotions registered no Min/Max strategy, so the cart put the
 * rule's full % on every eligible line. The server's answers for every cart below
 * are from nexus.local (fixtures-minmax-offline.json, posnext_promotions
 * apply_offers); the invoice saves rate × qty (G6, fixtures-minmax-buy-one.json).
 *
 * The strategy is posnext_promotions' own file, imported by path: the bench
 * sibling apps/posnext_promotions, or POSNEXT_PROMOTIONS_DIR (a worktree). The
 * strategy cases are skipped when neither is there; the safety net never needs it.
 * @vitest-environment jsdom
 */
import { existsSync, readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { createPinia, setActivePinia } from "pinia"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
	return { offers: null }
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: ({ url } = {}) => ({
		submit: vi.fn(async () => {
			if (String(url).endsWith("apply_offers")) return server.offers
			return {
				items: [],
				free_items: [],
				applied_pricing_rules: [],
				discount_amount: 0,
			}
		}),
		reload: vi.fn(),
		fetch: vi.fn(),
	}),
}))
vi.mock("@/utils/apiWrapper", () => ({ call: vi.fn(async () => []) }))
vi.mock("@/utils/offerStrategies", async (importOriginal) => ({
	...(await importOriginal()),
	loadOfferStrategyPlugins: async () => {},
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
vi.mock("@/utils/offline/db", () => ({
	getOneTimeRedemptions: async () => [],
	setOneTimeRedemptions: async () => {},
	addOneTimeRedemptions: async () => {},
}))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const fixture = (await import("./fixtures-minmax-offline.json")).default
const buyOneFixture = (await import("./fixtures-minmax-buy-one.json")).default
const { usePOSCartStore } = await import("../posCart")
const { usePOSOffersStore } = await import("../posOffers")
const { offlineState } = await import("@/utils/offline/offlineState")
const registry = await import("@/utils/offerStrategies")

const here = dirname(fileURLToPath(import.meta.url))
const promotionsDir =
	process.env.POSNEXT_PROMOTIONS_DIR ||
	resolve(here, "../../../../../posnext_promotions")
const strategyFile = resolve(
	promotionsDir,
	"posnext_promotions/public/pos/offer-strategies.js",
)
const hasPromotions = existsSync(strategyFile)
// Loaded as a data: URL: Vite will not load a computed path outside this app. The
// file imports nothing (see its header), so its source is the whole module.
const promotions = hasPromotions
	? await import(
			/* @vite-ignore */ `data:text/javascript;base64,${readFileSync(strategyFile).toString("base64")}`
		)
	: null

const ITEMS = {
	_PNXT_TEST_ITEM_A: { price: 50, brand: null },
	_PNXT_TEST_ITEM_B: { price: 80, brand: null },
	_PNXT_TEST_ITEM_C: { price: 20, brand: "_PNXT_TEST_BRAND" },
}

const round2 = (value) => Math.round(value * 100) / 100
const ruleNames = (value) =>
	(Array.isArray(value) ? value : String(value || "").split(","))
		.map((s) => s.trim())
		.filter(Boolean)

function addLine(cart, code, qty) {
	const { price, brand } = ITEMS[code]
	cart.addItem({
		item_code: code,
		item_name: code,
		item_group: "Products",
		brand,
		rate: price,
		price_list_rate: price,
		uom: "Nos",
		stock_uom: "Nos",
		conversion_factor: 1,
	})
	if (qty !== 1) cart.updateItemQuantity(code, qty)
}

async function settle(cart) {
	cart.forceRefreshOffers()
	await vi.waitFor(() =>
		expect(cart.offerProcessingState.isProcessing).toBe(false),
	)
	// Let the watcher's debounce (the pass changed discounts) run out too.
	await new Promise((r) => setTimeout(r, 150))
	await vi.waitFor(() =>
		expect(cart.offerProcessingState.isProcessing).toBe(false),
	)
}

const line = (cart, code) =>
	cart.invoiceItems.find((i) => i.item_code === code && !i.is_free_item)

/** The rows the offline sale sends, which the server saves at rate × qty. */
function sentRows(cart) {
	return cart.formatItemsForSubmission(cart.invoiceItems)
}

function expectServerLines(cart, expected) {
	for (const want of expected) {
		const got = line(cart, want.item_code)
		const msg = `${want.item_code} × ${want.qty}`
		expect(got.quantity, msg).toBe(want.qty)
		expect(got.amount, msg).toBe(want.amount)
		expect(got.discount_percentage || 0, msg).toBeCloseTo(
			want.discount_percentage,
			9,
		)
		const row = sentRows(cart).find((r) => r.item_code === want.item_code)
		expect(row.rate, msg).toBe(want.rate)
		expect(ruleNames(got.pricing_rules), msg).toEqual(
			ruleNames(want.pricing_rules),
		)
	}
	const saved = round2(
		expected.reduce((sum, l) => sum + round2(l.rate * l.qty), 0),
	)
	expect(cart.grandTotal).toBe(saved)
	expect(
		round2(sentRows(cart).reduce((sum, r) => sum + round2(r.rate * r.qty), 0)),
	).toBe(saved)
}

let cart
let offers
let warn

function freshCart(offer) {
	setActivePinia(createPinia())
	offers = usePOSOffersStore()
	offers.setAvailableOffers(offer ? [offer] : [])
	cart = usePOSCartStore()
	cart.posProfile = "_PNXT_TEST_POS_PROFILE__Test Company"
	cart.customer = "_PNXT_TEST_CUSTOMER"
	return cart
}

beforeEach(() => {
	registry.clearOfferStrategies()
	server.offers = null
	vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(true)
	warn = vi.spyOn(console, "warn").mockImplementation(() => {})
})
afterEach(() => vi.restoreAllMocks())

function registerPromotions() {
	promotions.register({
		registerOfferStrategy: registry.registerOfferStrategy,
		registerProductOfferStrategy: registry.registerProductOfferStrategy,
	})
}

describe("G7 safety net: a Min/Max offer with no strategy is skipped offline", () => {
	it("buy one on 6 × 50 sells at the full 300.00, and warns once", async () => {
		const minWarnings = () =>
			warn.mock.calls.filter(([msg]) => String(msg).includes('"Min"')).length
		freshCart(fixture.rules._PNXT_G7_BuyOneA.offer)
		addLine(cart, "_PNXT_TEST_ITEM_A", 6)
		await settle(cart)
		const a = line(cart, "_PNXT_TEST_ITEM_A")
		expect(a.amount).toBe(300)
		expect(a.discount_percentage || 0).toBe(0)
		expect(ruleNames(a.pricing_rules)).toEqual([])
		expect(cart.grandTotal).toBe(300)
		expect(cart.appliedOffers).toHaveLength(0)
		// The first skip in this module warns (the warning is once per mode, per page).
		expect(minWarnings()).toBe(1)

		cart.updateItemQuantity("_PNXT_TEST_ITEM_A", 7)
		await settle(cart)
		expect(cart.grandTotal).toBe(350)
		expect(minWarnings()).toBe(1)
	})

	it("a group-wide Min rule frees no line: A, B and C all at full price", async () => {
		freshCart(fixture.rules._PNXT_G7_MinGroup.offer)
		addLine(cart, "_PNXT_TEST_ITEM_A", 2)
		addLine(cart, "_PNXT_TEST_ITEM_B", 2)
		addLine(cart, "_PNXT_TEST_ITEM_C", 3)
		await settle(cart)
		expect(cart.grandTotal).toBe(2 * 50 + 2 * 80 + 3 * 20)
		expect(cart.invoiceItems.every((i) => !(i.discount_percentage > 0))).toBe(
			true,
		)
	})

	it("a Max rule with no strategy is skipped too", async () => {
		freshCart(fixture.rules._PNXT_G7_MaxAB.offer)
		addLine(cart, "_PNXT_TEST_ITEM_A", 2)
		addLine(cart, "_PNXT_TEST_ITEM_B", 2)
		await settle(cart)
		expect(cart.grandTotal).toBe(260)
	})

	/** Price the cart online with the server's answer, then go offline. */
	async function pricedOnline(offer, lines, answer) {
		vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(false)
		freshCart(offer)
		for (const [code, qty] of lines) addLine(cart, code, qty)
		cart.cancelPendingOfferProcessing()
		server.offers = {
			items: answer.map((l) => ({
				...l,
				discount_source: "pricing_rule",
				is_already_discounted: 0,
			})),
			free_items: [],
			applied_pricing_rules: [offer.name],
		}
		await cart.applyOffer(offer, cart.posProfile)
		vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(true)
	}

	it("a one-unit winner priced online at 100%, raised to 4 offline, is not 4 free units", async () => {
		const { offer, cases } = fixture.rules._PNXT_G7_MinAB
		const { cart: lines, lines: answer } = cases.find((c) => c.cart[0][1] === 1)
		await pricedOnline(offer, lines, answer)
		expect(line(cart, "_PNXT_TEST_ITEM_A").amount).toBe(0)

		cart.updateItemQuantity("_PNXT_TEST_ITEM_A", 4)
		await settle(cart)
		expect(line(cart, "_PNXT_TEST_ITEM_A").amount).toBe(200)
		expect(ruleNames(line(cart, "_PNXT_TEST_ITEM_A").pricing_rules)).toEqual([])
		expect(cart.grandTotal).toBe(200 + 240)
		expect(cart.appliedOffers).toHaveLength(0)
	})

	it("a line priced online at 6, raised to 7 offline, drops the stale % (350.00, not 291.69)", async () => {
		const offer = {
			...fixture.rules._PNXT_G7_BuyOneA.offer,
			name: buyOneFixture.rule,
		}
		const { line: online } = buyOneFixture.cases.find((c) => c.qty === 6)
		await pricedOnline(offer, [["_PNXT_TEST_ITEM_A", 6]], [online])
		expect(cart.grandTotal).toBe(250.02)

		cart.updateItemQuantity("_PNXT_TEST_ITEM_A", 7)
		await settle(cart)
		expect(cart.grandTotal).toBe(350)
	})
})

// A sibling checkout older than G7 has no Min/Max strategy: skip, don't fail.
describe.skipIf(!promotions?.minMaxStrategy)(
	"G7: offline Min/Max matches what the server saves",
	() => {
		beforeEach(registerPromotions)

		for (const [title, { offer, cases }] of Object.entries(fixture.rules)) {
			for (const { cart: lines, applied, lines: expected } of cases) {
				const label = lines
					.map(([code, qty]) => `${code.slice(-1)}×${qty}`)
					.join(" + ")
				it(`${title} ${offer.apply_discount_on_price} on ${label}`, async () => {
					freshCart(offer)
					for (const [code, qty] of lines) addLine(cart, code, qty)
					await settle(cart)
					expectServerLines(cart, expected)
					expect(cart.appliedOffers.map((o) => o.code)).toEqual(applied)
				})
			}
		}

		it("buy one on 6 × 50 is 250.02, not 0.00", async () => {
			freshCart(fixture.rules._PNXT_G7_BuyOneA.offer)
			addLine(cart, "_PNXT_TEST_ITEM_A", 6)
			await settle(cart)
			expect(line(cart, "_PNXT_TEST_ITEM_A").amount).toBe(250.02)
			expect(cart.grandTotal).toBe(250.02)
		})

		it("a qty change offline prices the line again: 6 → 7 → 3 → 1", async () => {
			const { offer, cases } = fixture.rules._PNXT_G7_BuyOneA
			freshCart(offer)
			addLine(cart, "_PNXT_TEST_ITEM_A", 6)
			for (const qty of [6, 7, 3, 1]) {
				cart.updateItemQuantity("_PNXT_TEST_ITEM_A", qty)
				await settle(cart)
				const { lines: expected, applied } = cases.find(
					(c) => c.cart[0][1] === qty,
				)
				expectServerLines(cart, expected)
				expect(cart.appliedOffers.map((o) => o.code)).toEqual(applied)
			}
		})

		it("a cheaper line added offline takes the discount; the dearer line goes back to full price", async () => {
			const { offer, cases } = fixture.rules._PNXT_G7_MinAB
			freshCart(offer)
			addLine(cart, "_PNXT_TEST_ITEM_B", 3)
			await settle(cart)
			// B alone, 3 units: B is the cheapest line in scope (80 × 3, one free: 53.33 a unit).
			expect(line(cart, "_PNXT_TEST_ITEM_B").amount).toBe(159.99)
			addLine(cart, "_PNXT_TEST_ITEM_A", 2)
			await settle(cart)
			expectServerLines(
				cart,
				cases.find((c) => c.cart[0][0] === "_PNXT_TEST_ITEM_B").lines,
			)
		})

		it("a line priced online, then changed in qty offline, drops the stale blended % (6 → 7 is 300.02)", async () => {
			vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(false)
			const offer = {
				...fixture.rules._PNXT_G7_BuyOneA.offer,
				name: buyOneFixture.rule,
			}
			freshCart(offer)
			addLine(cart, "_PNXT_TEST_ITEM_A", 6)
			cart.cancelPendingOfferProcessing()
			const { line: online } = buyOneFixture.cases.find((c) => c.qty === 6)
			server.offers = {
				items: [{ ...online }],
				free_items: [],
				applied_pricing_rules: [buyOneFixture.rule],
			}
			await cart.applyOffer(offer, cart.posProfile)
			expect(line(cart, "_PNXT_TEST_ITEM_A").amount).toBe(250.02)

			vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(true)
			cart.updateItemQuantity("_PNXT_TEST_ITEM_A", 7)
			await settle(cart)
			const want = buyOneFixture.cases.find((c) => c.qty === 7)
			expect(line(cart, "_PNXT_TEST_ITEM_A").amount).toBe(want.invoice.amount)
			expect(sentRows(cart)[0].rate).toBe(want.invoice.rate)
			expect(cart.grandTotal).toBe(want.invoice.grand_total)
		})
	},
)
