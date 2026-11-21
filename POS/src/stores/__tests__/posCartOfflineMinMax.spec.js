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
	return { offers: null, inFlight: null }
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: ({ url } = {}) => ({
		submit: vi.fn(async () => {
			if (String(url).endsWith("apply_offers")) {
				// A cashier's change while the request is in flight (round 2, I-1r).
				const change = server.inFlight
				server.inFlight = null
				change?.()
				return server.offers
			}
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
		// The flags the server stamps (mark_item_discount_flags), which later passes read.
		expect(got.discount_source || "", msg).toBe(want.discount_source)
		expect(Number(got.is_already_discounted || 0), msg).toBe(
			want.is_already_discounted,
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
	server.inFlight = null
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

/**
 * Price the cart online with the server's answer (its lines carry the
 * discount_source / is_already_discounted the server stamped), then go offline.
 */
async function pricedOnline(
	offer,
	lines,
	answer,
	applied = [offer.name],
	inFlight = null,
) {
	vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(false)
	freshCart(offer)
	for (const [code, qty] of lines) addLine(cart, code, qty)
	cart.cancelPendingOfferProcessing()
	server.offers = {
		items: answer.map((l) => ({ ...l })),
		free_items: [],
		applied_pricing_rules: applied,
	}
	server.inFlight = inFlight
	await cart.applyOffer(offer, cart.posProfile)
	// The connection drops before any later pass reaches the server.
	cart.cancelPendingOfferProcessing()
	vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(true)
}

const rule = (title) => fixture.rules[title]
const serverCase = (title, cartLines) =>
	rule(title).cases.find(
		(c) => JSON.stringify(c.cart) === JSON.stringify(cartLines),
	)
const A = "_PNXT_TEST_ITEM_A"
const B = "_PNXT_TEST_ITEM_B"

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

	it("a line outside the offer's scope added offline keeps the server's 250.02 (I-1)", async () => {
		const { offer } = rule("_PNXT_G7_BuyOneA")
		await pricedOnline(
			offer,
			[[A, 6]],
			serverCase("_PNXT_G7_BuyOneA", [[A, 6]]).lines,
		)
		expect(cart.grandTotal).toBe(250.02)

		addLine(cart, B, 1)
		await settle(cart)
		expect(line(cart, A).amount).toBe(250.02)
		expect(cart.grandTotal).toBe(250.02 + 80)
		expect(cart.appliedOffers.map((o) => o.code)).toEqual([offer.name])
	})

	it("a customer change offline keeps the server's 250.02 (I-1)", async () => {
		const { offer } = rule("_PNXT_G7_BuyOneA")
		await pricedOnline(
			offer,
			[[A, 6]],
			serverCase("_PNXT_G7_BuyOneA", [[A, 6]]).lines,
		)
		cart.customer = "_PNXT_TEST_OTHER_CUSTOMER"
		await settle(cart)
		expect(line(cart, A).amount).toBe(250.02)
		expect(cart.grandTotal).toBe(250.02)
	})

	it("a cashier's own % on a line the offer leaves keeps the %, only the rule comes off (m-10)", async () => {
		const { offer } = rule("_PNXT_G7_BuyOneA")
		await pricedOnline(
			offer,
			[[A, 6]],
			serverCase("_PNXT_G7_BuyOneA", [[A, 6]]).lines,
		)
		Object.assign(line(cart, A), {
			discount_percentage: 10,
			discount_source: "manual_discount",
			is_already_discounted: 1,
		})
		cart.updateItemQuantity(A, 7)
		await settle(cart)
		const a = line(cart, A)
		expect(ruleNames(a.pricing_rules)).toEqual([])
		expect(a.discount_percentage).toBe(10)
		expect(a.amount).toBe(315)
	})

	const accumulative = {
		...rule("_PNXT_G7_MinAB").offer,
		name: "_PNXT_G7_ACCUM",
		apply_discount_on_price: "Accumulative",
		accumulative_scope_field: "item_code",
		accumulative_scopes: [
			{ values: [A], discount_percentage: 10 },
			{ values: [B], discount_percentage: 5 },
		],
		min_qty: 0,
	}
	const accumulativeAnswer = (qa, qb) => [
		{
			item_code: A,
			qty: qa,
			price_list_rate: 50,
			discount_percentage: 15,
			rate: 42.5,
			amount: 42.5 * qa,
			pricing_rules: accumulative.name,
			discount_source: "accumulative_promotion",
			is_already_discounted: 1,
		},
		{
			item_code: B,
			qty: qb,
			price_list_rate: 80,
			discount_percentage: 15,
			rate: 68,
			amount: 68 * qb,
			pricing_rules: accumulative.name,
			discount_source: "accumulative_promotion",
			is_already_discounted: 1,
		},
	]

	it("an Accumulative offer keeps its % on a qty change: only which scopes are present matters (I-1)", async () => {
		await pricedOnline(
			accumulative,
			[
				[A, 2],
				[B, 1],
			],
			accumulativeAnswer(2, 1),
		)
		expect(cart.grandTotal).toBe(85 + 68)
		cart.updateItemQuantity(A, 3)
		await settle(cart)
		expect(line(cart, A).amount).toBe(127.5)
		expect(cart.grandTotal).toBe(127.5 + 68)
	})

	it("an answer for A×1 + B×3 that returns after A was raised to 4 is not kept offline: never 4 free units (I-1r)", async () => {
		const title = "_PNXT_G7_MinAB"
		const first = serverCase(title, [
			[A, 1],
			[B, 3],
		])
		await pricedOnline(
			rule(title).offer,
			first.cart,
			first.lines,
			undefined,
			() => cart.updateItemQuantity(A, 4),
		)
		// The stale answer is dropped, not applied (the request's cart is gone).
		expect(cart.appliedOffers).toHaveLength(0)
		expect(line(cart, A).discount_percentage || 0).toBe(0)
		cart.customer = "_PNXT_TEST_OTHER_CUSTOMER"
		await settle(cart)
		expect(line(cart, A).quantity).toBe(4)
		expect(line(cart, A).amount).toBe(200)
		expect(cart.grandTotal).toBe(200 + 240)
	})

	it("an offer removed while the cart changes in flight comes off its lines, and stays off offline (m-r2-1)", async () => {
		const buyOne = rule("_PNXT_G7_BuyOneA").offer
		const tenOffB = {
			...buyOne,
			name: "_PNXT_G7_TEN_OFF_B",
			title: "_PNXT_G7_TEN_OFF_B",
			apply_discount_on_price: null,
			min_or_max_discount_qty_limit: 0,
			min_qty: 0,
			discount_percentage: 10,
			eligible_items: [B],
		}
		const aLine = serverCase("_PNXT_G7_BuyOneA", [[A, 6]]).lines[0]
		const bLine = (qty) => ({
			item_code: B,
			qty,
			price_list_rate: 80,
			discount_percentage: 10,
			rate: 72,
			amount: 72 * qty,
			pricing_rules: tenOffB.name,
			discount_source: "pricing_rule",
			is_already_discounted: 0,
		})
		vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(false)
		freshCart(buyOne)
		offers.setAvailableOffers([buyOne, tenOffB])
		addLine(cart, A, 6)
		addLine(cart, B, 2)
		cart.cancelPendingOfferProcessing()
		server.offers = {
			items: [{ ...aLine }, bLine(2)],
			free_items: [],
			applied_pricing_rules: [buyOne.name, tenOffB.name],
		}
		await cart.applyOffer(buyOne, cart.posProfile)
		await cart.applyOffer(tenOffB, cart.posProfile)
		expect(cart.appliedOffers.map((o) => o.code).sort()).toEqual(
			[buyOne.name, tenOffB.name].sort(),
		)
		expect(line(cart, A).amount).toBe(250.02)

		// Remove buy one; B changes while the request is in flight, so the answer is dropped.
		server.inFlight = () => cart.updateItemQuantity(B, 3)
		await cart.removeOffer(buyOne, cart.posProfile)
		cart.cancelPendingOfferProcessing()
		vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(true)
		expect(cart.appliedOffers.map((o) => o.code)).toEqual([tenOffB.name])
		expect(ruleNames(line(cart, A).pricing_rules)).toEqual([])
		expect(line(cart, A).amount).toBe(300)

		cart.customer = "_PNXT_TEST_OTHER_CUSTOMER"
		await settle(cart)
		expect(line(cart, A).amount).toBe(300)
		expect(cart.appliedOffers.map((o) => o.code)).toEqual([tenOffB.name])
	})

	it("an answer for A×6 that returns after A was raised to 7 is not kept offline: never a stale 291.69 (I-1r)", async () => {
		const title = "_PNXT_G7_BuyOneA"
		const first = serverCase(title, [[A, 6]])
		await pricedOnline(
			rule(title).offer,
			first.cart,
			first.lines,
			undefined,
			() => cart.updateItemQuantity(A, 7),
		)
		cart.customer = "_PNXT_TEST_OTHER_CUSTOMER"
		await settle(cart)
		expect(line(cart, A).quantity).toBe(7)
		expect(cart.grandTotal).toBe(350)
	})

	it("an Accumulative line released when a scope leaves the cart drops its accumulative flag (m-3)", async () => {
		await pricedOnline(
			accumulative,
			[
				[A, 2],
				[B, 1],
			],
			accumulativeAnswer(2, 1),
		)
		expect(line(cart, A).is_accumulative_discount).toBe(1)
		cart.removeItem(B)
		await settle(cart)
		const a = line(cart, A)
		expect(a.amount).toBe(100)
		expect(a.is_accumulative_discount || 0).toBe(0)
		expect(a.is_already_discounted || 0).toBe(0)
	})
})

// POSNEXT_PROMOTIONS_DIR (CI) demands the strategy: a missing file or a checkout
// older than G7 fails there. A bench sibling without it is skipped instead.
const requirePromotions = Boolean(process.env.POSNEXT_PROMOTIONS_DIR)
it.runIf(requirePromotions)(
	"POSNEXT_PROMOTIONS_DIR holds promotions' Min/Max strategy",
	() => {
		expect(hasPromotions, strategyFile).toBe(true)
		expect(typeof promotions?.minMaxStrategy?.apply).toBe("function")
	},
)

describe.skipIf(!requirePromotions && !promotions?.minMaxStrategy)(
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

		it("Item Level Discount: priced online on A×1 + B×3, A raised to 4 offline is the server's 390 (C-1)", async () => {
			const title = "_PNXT_G7_MinAB_ItemLevel"
			const first = serverCase(title, [
				[A, 1],
				[B, 3],
			])
			await pricedOnline(rule(title).offer, first.cart, first.lines)
			expect(line(cart, A).amount).toBe(0)
			expect(line(cart, A).discount_source).toBe("item_level_promotion")

			cart.updateItemQuantity(A, 4)
			await settle(cart)
			expectServerLines(
				cart,
				serverCase(title, [
					[A, 4],
					[B, 3],
				]).lines,
			)
			expect(cart.grandTotal).toBe(390)
		})

		it("Item Level Discount: priced online at 6, 7 offline is the server's 300.02 (C-1)", async () => {
			const title = "_PNXT_G7_BuyOneA_ItemLevel"
			const first = serverCase(title, [[A, 6]])
			await pricedOnline(rule(title).offer, first.cart, first.lines)
			expect(cart.grandTotal).toBe(250.02)

			cart.updateItemQuantity(A, 7)
			await settle(cart)
			expectServerLines(cart, serverCase(title, [[A, 7]]).lines)
		})

		it("Auto Discount: lines the rule stamped auto_discount, A raised to 4 offline, sell at the server's full price (C-1)", async () => {
			// apply_offers never applies an Auto Discount Min/Max rule (the fixture), so
			// the stamp can only come from an older answer: the rule must still come off.
			const title = "_PNXT_G7_MinAB_Auto"
			const stamped = serverCase("_PNXT_G7_MinAB", [
				[A, 1],
				[B, 3],
			]).lines.map((l) => ({
				...l,
				discount_source: "auto_discount",
				is_already_discounted: 0,
			}))
			await pricedOnline(
				rule(title).offer,
				[
					[A, 1],
					[B, 3],
				],
				stamped,
			)
			expect(line(cart, A).amount).toBe(0)

			cart.updateItemQuantity(A, 4)
			await settle(cart)
			expectServerLines(
				cart,
				serverCase(title, [
					[A, 4],
					[B, 3],
				]).lines,
			)
			expect(cart.grandTotal).toBe(440)
			expect(cart.appliedOffers).toHaveLength(0)
		})

		it("Auto Discount: 6 → 7 offline sells at the server's full price, never a stale 291.69 (C-1)", async () => {
			const title = "_PNXT_G7_BuyOneA_Auto"
			const stamped = serverCase("_PNXT_G7_BuyOneA", [[A, 6]]).lines.map(
				(l) => ({
					...l,
					discount_source: "auto_discount",
				}),
			)
			await pricedOnline(rule(title).offer, [[A, 6]], stamped)
			cart.updateItemQuantity(A, 7)
			await settle(cart)
			expectServerLines(cart, serverCase(title, [[A, 7]]).lines)
		})

		it("a coupon line carrying the rule is ranked but never written; when it wins no other line is discounted (Q6)", async () => {
			const title = "_PNXT_G7_MinAB"
			const first = serverCase(title, [
				[A, 2],
				[B, 2],
			])
			await pricedOnline(rule(title).offer, first.cart, first.lines)
			const a = line(cart, A)
			Object.assign(a, {
				discount_source: "coupon",
				coupon_code: "_PNXT_G7_COUPON",
			})
			const before = {
				pct: a.discount_percentage,
				rules: ruleNames(a.pricing_rules),
			}

			cart.updateItemQuantity(B, 3)
			await settle(cart)
			expect(line(cart, A).discount_percentage).toBe(before.pct)
			expect(ruleNames(line(cart, A).pricing_rules)).toEqual(before.rules)
			expect(line(cart, B).amount).toBe(240)
			expect(line(cart, B).discount_percentage || 0).toBe(0)
		})
	},
)
