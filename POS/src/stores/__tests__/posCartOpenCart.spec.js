/**
 * D-4 / INV-2: the open cart survives a reload. It is saved to IndexedDB (debounced),
 * scoped to one user, POS Profile and opening shift, restored before the cart is
 * shown, and re-priced on restore. The server answers are the real ones from
 * nexus.local (fixtures-ff-bxgy-qty-1-2-1.json): an F&F customer with a BXGY item.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
	// invoice: what the server holds for the payment draft (null: no such invoice).
	// updateInvoice: answers update_invoice (the payment-open draft save).
	return { requests: [], invoice: { docstatus: 0 }, updateInvoice: null }
})

// The offline `settings` table, in memory. `broken` makes every call fail.
const storage = vi.hoisted(() => ({ rows: new Map(), broken: null }))

const fixture = (await import("./fixtures-ff-bxgy-qty-1-2-1.json")).default
const RULE = fixture.rule
const ITEM = fixture.apply_offers_qty2.items[0].item_code
const CUSTOMER = fixture.eligibility.customer

const clone = (value) => JSON.parse(JSON.stringify(value))
const ruleNames = (value) =>
	(Array.isArray(value) ? value : String(value || "").split(",")).map((s) => s.trim()).filter(Boolean)

vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: ({ url } = {}) => ({
		submit: vi.fn(async (params) => {
			if (String(url).includes("update_invoice")) {
				server.requests.push({ method: "update_invoice", params: clone(params) })
				return server.updateInvoice ? server.updateInvoice(params) : {}
			}
			if (!String(url).includes("apply_offers")) return {}
			server.requests.push({ method: "apply_offers", params: clone(params) })
			const paid = params.invoice_data.items.filter((i) => !i.is_free_item)
			const qty = paid.reduce((sum, i) => sum + Number(i.qty), 0)
			return clone(qty >= 2 ? fixture.apply_offers_qty2 : fixture.apply_offers_qty1)
		}),
		reload: vi.fn(),
		fetch: vi.fn(),
	}),
}))
vi.mock("@/utils/apiWrapper", () => ({
	call: vi.fn(async (method, params) => {
		if (method.includes("check_friends_and_family_eligibility")) {
			server.requests.push({ method: "eligibility", params: clone(params) })
			return clone(fixture.eligibility)
		}
		if (method.includes("apply_friends_and_family_discount")) {
			server.requests.push({ method: "fnf_only", params: clone(params) })
			const tagged = params.items.some((i) => ruleNames(i.pricing_rules).includes(RULE))
			return clone(tagged ? fixture.fnf_only_qty1_bxgy_tagged : fixture.fnf_only_qty1)
		}
		if (method === "frappe.client.get_value") {
			server.requests.push({ method: "get_value", params: clone(params) })
			if (server.invoice instanceof Error) throw server.invoice
			return server.invoice ? { name: params.filters?.name, ...clone(server.invoice) } : undefined
		}
		if (method.includes("validate_coupon")) {
			server.requests.push({ method: "validate_coupon", params: clone(params) })
			return { valid: true, line_updates: clone(LINE_COUPON.line_updates) }
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
vi.mock("@/utils/offline/db", () => {
	const guard = (fn) => (...args) => {
		if (storage.broken === "throw") throw new Error("IndexedDB is gone")
		if (storage.broken === "reject") return Promise.reject(new Error("QuotaExceededError"))
		if (storage.broken === "hang") return new Promise(() => {})
		return fn(...args)
	}
	return {
		db: {
			settings: {
				get: guard(async (key) => (storage.rows.has(key) ? clone(storage.rows.get(key)) : undefined)),
				put: guard(async (row) => {
					storage.rows.set(row.key, clone(row))
				}),
				delete: guard(async (key) => {
					storage.rows.delete(key)
				}),
				toArray: guard(async () => [...storage.rows.values()].map(clone)),
				bulkDelete: guard(async (keys) => {
					for (const key of keys) storage.rows.delete(key)
				}),
			},
		},
		getOneTimeRedemptions: async () => [],
		setOneTimeRedemptions: async () => {},
		addOneTimeRedemptions: async () => {},
	}
})
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("../posCart")
const { usePOSOffersStore } = await import("../posOffers")
const { isFnfLine } = await import("@/utils/friendsAndFamily")
const { offlineState } = await import("@/utils/offline/offlineState")
const { OPEN_CART_TAB_KEY, openCartSlotKey, resetOpenCartStorage } = await import("@/utils/offline/openCart")
const { usePaymentOpenCheck } = await import("@/composables/usePaymentOpenCheck")

const PROFILE = "_PNXT_TEST_POS_PROFILE__Test Company"
const SCOPE = { user: "cashier-a@example.com", pos_profile: PROFILE, pos_opening_shift: "POS-OPEN-1" }

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

const ITEM_A = {
	item_code: ITEM,
	item_name: "ITEM_A",
	rate: 50,
	price_list_rate: 50,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
}

// UIT-L50: a line coupon at 50% that beats F&F 30% on ITEM_A (U-18 b).
const LINE_COUPON = vi.hoisted(() => ({
	code: "UIT-L50",
	name: "UIT-L50",
	line_level: true,
	coupon: { discount_type: "Percentage", discount_percentage: 50 },
	line_updates: [
		{ line_key: 0, item_code: "_PNXT_TEST_ITEM_A", discount_percentage: 50, coupon_only_discount: 25 },
	],
}))

// An order coupon that beat F&F (calculate_coupon_discount → suppress_friends_and_family).
const ORDER_COUPON = {
	code: "UIT-O40",
	name: "UIT-O40",
	percentage: 40,
	suppress_friends_and_family: true,
	fnf_message: { message: "Coupon UIT-O40 applied instead of Friends & Family" },
}

const paidLine = (cart) => cart.invoiceItems.find((i) => !i.is_free_item)
const freeRows = (cart) => cart.invoiceItems.filter((i) => i.is_free_item)
const saved = () => storage.rows.get(openCartSlotKey())?.value || null
const setSaved = (value) => storage.rows.set(openCartSlotKey(), { key: openCartSlotKey(), value })
const X = "ACC-SINV-2026-00042"
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function settle(cart, seen) {
	await vi.waitFor(
		() => {
			expect(server.requests.length).toBeGreaterThan(seen)
			expect(cart.offerProcessingState.isProcessing).toBe(false)
		},
		{ timeout: 3000, interval: 20 }
	)
	await wait(150)
	await vi.waitFor(() => expect(cart.offerProcessingState.isProcessing).toBe(false))
}

/** A fresh Pinia: what the page has after F5. */
function freshCart() {
	setActivePinia(createPinia())
	usePOSOffersStore().setAvailableOffers([BXGY_OFFER])
	const cart = usePOSCartStore()
	cart.posProfile = PROFILE
	cart.posOpeningShift = SCOPE.pos_opening_shift
	return cart
}

/** The F&F customer with ITEM_A × qty, priced by the server and saved. */
async function pricedCart(qty = 1) {
	const cart = freshCart()
	expect(await cart.restoreOpenCart(SCOPE)).toBe(false) // nothing saved: persistence armed
	cart.customer = CUSTOMER
	cart.addItem(ITEM_A)
	await settle(cart, 0)
	if (qty !== 1) {
		const seen = server.requests.length
		cart.updateItemQuantity(ITEM, qty)
		await settle(cart, seen)
	}
	await vi.waitFor(() => expect(saved()?.items?.length).toBe(cart.invoiceItems.length), { timeout: 2000 })
	return cart
}

describe("the open cart survives a reload (D-4)", () => {
	beforeEach(() => {
		server.requests = []
		storage.rows = new Map()
		storage.broken = null
		server.invoice = { docstatus: 0 }
		server.updateInvoice = null
		sessionStorage.setItem(OPEN_CART_TAB_KEY, "tab-1")
		resetOpenCartStorage()
		vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(false)
	})
	afterEach(() => {
		vi.restoreAllMocks()
	})

	it("saves the cart in the draft shape with its scope, and restores it after F5", async () => {
		const before = await pricedCart()
		expect(isFnfLine(paidLine(before))).toBe(true)

		const record = saved()
		expect(record.pos_profile).toBe(PROFILE)
		expect(record.scope).toEqual(SCOPE)
		expect(record.customer).toBe(CUSTOMER)
		expect(record.items).toHaveLength(1)
		expect(record.items[0].discount_source).toBe("friends_and_family")
		expect(record).toHaveProperty("applied_offers")
		expect(record).toHaveProperty("applied_coupon")

		const cart = freshCart()
		expect(cart.invoiceItems).toHaveLength(0)
		expect(await cart.restoreOpenCart(SCOPE)).toBe(true)
		// Shown as it was, before any server answer.
		expect(cart.customer).toBe(CUSTOMER)
		expect(cart.invoiceItems).toHaveLength(1)
		expect(isFnfLine(paidLine(cart))).toBe(true)
		expect(paidLine(cart).amount).toBeCloseTo(35, 2)
		expect(cart.fnfEligibility?.eligible).toBe(true)
	})

	it("keeps the server-checked draft name, but not the payment check", async () => {
		await pricedCart()
		setSaved({ ...saved(), payment_draft_name: X })
		const cart = freshCart()
		await cart.restoreOpenCart(SCOPE)
		expect(cart.paymentDraftName).toBe(X)
		// The payment-open check (8o) runs again: payment collects the cart's own total.
		expect(cart.paymentTotal).toBeCloseTo(cart.roundedTotal, 2)
	})

	it("re-prices the restored cart: F&F is asked again and the line stays F&F", async () => {
		await pricedCart()
		server.requests = []
		const cart = freshCart()
		await cart.restoreOpenCart(SCOPE)
		await settle(cart, 0)
		expect(server.requests.some((r) => r.method === "eligibility")).toBe(true)
		expect(server.requests.some((r) => r.method === "apply_offers" || r.method === "fnf_only")).toBe(true)
		expect(isFnfLine(paidLine(cart))).toBe(true)
		expect(paidLine(cart).amount).toBeCloseTo(35, 2)
	})

	it("INV-2 on a BXGY cart: one free row before and after the reload and re-price", async () => {
		const before = await pricedCart(2)
		expect(freeRows(before)).toHaveLength(1)
		expect(saved().items.filter((i) => i.is_free_item)).toHaveLength(1)

		server.requests = []
		const cart = freshCart()
		await cart.restoreOpenCart(SCOPE)
		expect(freeRows(cart)).toHaveLength(1)
		await settle(cart, 0)
		expect(server.requests.some((r) => r.method === "apply_offers")).toBe(true)
		expect(freeRows(cart)).toHaveLength(1)
		expect(paidLine(cart).quantity).toBe(2)
		expect(ruleNames(paidLine(cart).pricing_rules)).toEqual([RULE])
		expect(cart.appliedOffers.map((o) => o.code)).toEqual([RULE])
	})

	it("offline: restores without a server and re-prices once the POS is back online", async () => {
		await pricedCart()
		server.requests = []
		const offline = vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(true)
		const cart = freshCart()
		expect(await cart.restoreOpenCart(SCOPE)).toBe(true)
		await wait(400)
		expect(server.requests).toHaveLength(0)
		expect(isFnfLine(paidLine(cart))).toBe(true)
		expect(cart.fnfEligibility?.eligible).toBe(true)

		offline.mockReturnValue(false)
		offlineState._notifyChange("test")
		await settle(cart, 0)
		expect(server.requests.some((r) => r.method === "eligibility")).toBe(true)
		expect(isFnfLine(paidLine(cart))).toBe(true)
	})

	it("clears the saved cart when the sale completes", async () => {
		const cart = await pricedCart()
		cart.clearCart({ returnSerials: false }) // what both sale-complete paths call
		await vi.waitFor(() => expect(saved()).toBeNull())
		await wait(400)
		expect(saved()).toBeNull()
	})

	it("clears the saved cart when the cart is cleared, even with a save still pending", async () => {
		const cart = await pricedCart()
		cart.updateItemQuantity(ITEM, 3) // schedules a save
		cart.clearCart()
		await wait(600)
		expect(saved()).toBeNull()

		const next = freshCart()
		expect(await next.restoreOpenCart(SCOPE)).toBe(false)
		expect(next.invoiceItems).toHaveLength(0)
	})

	it("clears the saved cart when the shift closes, and saves nothing until the next shift", async () => {
		const cart = await pricedCart()
		await cart.stopCartPersistence()
		expect(saved()).toBeNull()
		expect(cart.invoiceItems).toHaveLength(0)
		cart.addItem(ITEM_A)
		await wait(600)
		expect(saved()).toBeNull()
	})

	it("never restores a cart from another shift or POS Profile", async () => {
		await pricedCart()
		const cart = freshCart()
		expect(await cart.restoreOpenCart({ ...SCOPE, pos_opening_shift: "POS-OPEN-2" })).toBe(false)
		expect(cart.invoiceItems).toHaveLength(0)
		expect(saved()).toBeNull()

		await pricedCart()
		const other = freshCart()
		expect(await other.restoreOpenCart({ ...SCOPE, pos_profile: "Other Profile" })).toBe(false)
		expect(other.invoiceItems).toHaveLength(0)
		expect(saved()).toBeNull()
	})

	it("never shows one cashier's cart to another cashier on the same browser", async () => {
		await pricedCart()
		const cart = freshCart()
		expect(await cart.restoreOpenCart({ ...SCOPE, user: "cashier-b@example.com" })).toBe(false)
		expect(cart.invoiceItems).toHaveLength(0)
		expect(cart.customer).not.toBe(CUSTOMER)
		// Cashier A's cart is gone, not just hidden.
		expect(saved()).toBeNull()
	})

	it("restores nothing without a complete scope (no user, no shift)", async () => {
		await pricedCart()
		const cart = freshCart()
		expect(await cart.restoreOpenCart({ ...SCOPE, user: null })).toBe(false)
		expect(cart.invoiceItems).toHaveLength(0)
	})

	it("does not save a cart loaded to edit an offline invoice", async () => {
		const cart = await pricedCart()
		await cart.suspendCartPersistence()
		expect(saved()).toBeNull()
		cart.updateItemQuantity(ITEM, 3)
		await wait(600)
		expect(saved()).toBeNull()
		// The next sale is saved again.
		cart.clearCart()
		cart.addItem(ITEM_A)
		await vi.waitFor(() => expect(saved()?.items?.length).toBeGreaterThan(0), { timeout: 2000 })
	})

	it("INV-2 on a line coupon that beat F&F (U-18 b): the coupon survives and is re-checked", async () => {
		const before = await pricedCart()
		before.applyDiscountToCart(clone(LINE_COUPON))
		expect(paidLine(before).coupon_code).toBe("UIT-L50")
		expect(paidLine(before).amount).toBeCloseTo(25, 2)
		await vi.waitFor(() => expect(saved()?.applied_coupon?.code).toBe("UIT-L50"), { timeout: 2000 })
		await wait(600) // the coupon re-check after the change settles

		server.requests = []
		const cart = freshCart()
		await cart.restoreOpenCart(SCOPE)
		expect(cart.appliedCoupon?.code).toBe("UIT-L50")
		expect(paidLine(cart).coupon_code).toBe("UIT-L50")
		expect(paidLine(cart).amount).toBeCloseTo(25, 2)
		await settle(cart, 0)
		await vi.waitFor(
			() => expect(server.requests.some((r) => r.method === "validate_coupon")).toBe(true),
			{ timeout: 2000 }
		)
		await vi.waitFor(() => expect(cart.offerProcessingState.isProcessing).toBe(false))
		expect(cart.appliedCoupon?.code).toBe("UIT-L50")
		expect(paidLine(cart).coupon_code).toBe("UIT-L50")
		expect(paidLine(cart).discount_source).toBe("coupon")
		expect(paidLine(cart).amount).toBeCloseTo(25, 2)
		expect(cart.invoiceItems).toHaveLength(1)
	})

	it("an order coupon that beat F&F survives the reload, is re-checked, and F&F stays off", async () => {
		const before = await pricedCart()
		before.applyDiscountToCart(clone(ORDER_COUPON))
		expect(isFnfLine(paidLine(before))).toBe(false)
		expect(before.additionalDiscount).toBeCloseTo(20, 2)
		await vi.waitFor(() => expect(saved()?.applied_coupon?.code).toBe("UIT-O40"), { timeout: 2000 })
		await wait(400)

		server.requests = []
		const cart = freshCart()
		await cart.restoreOpenCart(SCOPE)
		expect(cart.appliedCoupon?.code).toBe("UIT-O40")
		expect(cart.additionalDiscount).toBeCloseTo(20, 2)
		expect(cart.fnfCouponOverride?.code).toBe("UIT-O40")
		await settle(cart, 0)
		await vi.waitFor(() =>
			expect(server.requests.some((r) => r.method === "validate_coupon")).toBe(true)
		)
		expect(cart.appliedCoupon?.code).toBe("UIT-O40")
		expect(cart.additionalDiscount).toBeCloseTo(20, 2)
		// The server answered with F&F; the coupon that beat it keeps it off the line.
		expect(isFnfLine(paidLine(cart))).toBe(false)
		expect(cart.fnfResult).toBeNull()
	})

	// ── Fix round 1 (Ruling 136) ────────────────────────────────────────────────

	it("C1 (a): online, a restored cart whose draft was already submitted is closed, not sold again", async () => {
		await pricedCart()
		setSaved({ ...saved(), payment_draft_name: X })
		server.invoice = { docstatus: 1, grand_total: 40.25, rounded_total: 40.25, paid_amount: 40.25 }
		server.requests = []
		const cart = freshCart()
		expect(await cart.restoreOpenCart(SCOPE)).toBe(false)
		expect(server.requests.find((r) => r.method === "get_value")?.params.filters).toEqual({ name: X })
		expect(cart.invoiceItems).toHaveLength(0)
		expect(cart.paymentDraftName).toBeNull()
		expect(saved()).toBeNull()
		expect(cart.alreadySubmittedInvoice).toMatchObject({ name: X, grand_total: 40.25 })
		await wait(400)
		expect(server.requests.some((r) => r.method === "apply_offers" || r.method === "fnf_only")).toBe(false)
	})

	it("C1 (a): a restored draft that was cleaned up is not reused; a draft still open is", async () => {
		await pricedCart()
		setSaved({ ...saved(), payment_draft_name: X })
		server.invoice = null
		const gone = freshCart()
		expect(await gone.restoreOpenCart(SCOPE)).toBe(true)
		expect(gone.paymentDraftName).toBeNull()
		expect((await gone.ensurePaymentAllowed()).allowed).toBe(true)

		await gone.restoreOpenCart(SCOPE) // re-arm
		setSaved({ ...saved(), payment_draft_name: X })
		server.invoice = { docstatus: 0 }
		const open = freshCart()
		expect(await open.restoreOpenCart(SCOPE)).toBe(true)
		expect(open.paymentDraftName).toBe(X)
		expect((await open.ensurePaymentAllowed()).allowed).toBe(true)
	})

	it("C1 (c): the docstatus-1 error never starts a new draft; it closes the cart as already submitted", async () => {
		const cart = await pricedCart()
		cart.paymentDraftName = X
		server.updateInvoice = (params) => {
			if (params.data?.name) {
				const error = new Error("Cannot change docstatus from 1 (Submitted) to 0 (Draft)")
				error.exc_type = "DocstatusTransitionError"
				throw error
			}
			return { name: "ACC-SINV-NEW", grand_total: 40.25, items: [] }
		}
		server.invoice = { docstatus: 1, grand_total: 40.25, rounded_total: 40.25, paid_amount: 40.25 }
		server.requests = []
		const result = await cart.checkPriceBeforePayment()
		expect(result).toMatchObject({ checked: false, changed: false, alreadySubmitted: true })
		const saves = server.requests.filter((r) => r.method === "update_invoice")
		expect(saves).toHaveLength(1) // no fallback save without the name
		expect(saves[0].params.data.name).toBe(X)
		expect(cart.invoiceItems).toHaveLength(0)
		expect(cart.alreadySubmittedInvoice?.name).toBe(X)
		await vi.waitFor(() => expect(saved()).toBeNull())
	})

	it("C1 (c): the payment dialog does not open for an already-submitted cart", async () => {
		const openPayment = vi.fn()
		const showError = vi.fn()
		const check = usePaymentOpenCheck({
			isOffline: () => false,
			checkPrice: async () => ({ checked: false, changed: false, alreadySubmitted: true }),
			openPayment,
			showError,
		})
		expect(await check.requestPayment()).toBe(false)
		expect(await check.recheckAfterRefusal("refused")).toBe(true)
		expect(openPayment).not.toHaveBeenCalled()
		expect(showError).not.toHaveBeenCalled()
	})

	it("C1 (b): offline, a restored cart with a draft blocks payment until the draft is checked online", async () => {
		await pricedCart()
		setSaved({ ...saved(), payment_draft_name: X })
		server.requests = []
		const offline = vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(true)
		const cart = freshCart()
		expect(await cart.restoreOpenCart(SCOPE)).toBe(true)
		const blocked = await cart.ensurePaymentAllowed()
		expect(blocked.allowed).toBe(false)
		expect(blocked.message).toContain(X)
		expect(cart.paymentBlockedMessage).toContain(X)
		expect(server.requests).toHaveLength(0)

		server.invoice = { docstatus: 0 }
		offline.mockReturnValue(false)
		offlineState._notifyChange("test")
		await vi.waitFor(() => expect(cart.paymentBlockedMessage).toBe(""), { timeout: 2000 })
		expect((await cart.ensurePaymentAllowed()).allowed).toBe(true)
		expect(cart.paymentDraftName).toBe(X)
	})

	it("C1 (b): online, a draft that cannot be checked blocks payment too", async () => {
		await pricedCart()
		setSaved({ ...saved(), payment_draft_name: X })
		server.invoice = new Error("Network error")
		const cart = freshCart()
		expect(await cart.restoreOpenCart(SCOPE)).toBe(true)
		expect((await cart.ensurePaymentAllowed()).allowed).toBe(false)
		server.invoice = { docstatus: 0 }
		expect((await cart.ensurePaymentAllowed()).allowed).toBe(true)
	})

	it("C1 (d): the cart's offline_id is saved at once and reused after a restore", async () => {
		const cart = await pricedCart()
		const id = await cart.checkoutOfflineId()
		expect(id).toMatch(/^pos_offline_/)
		expect(saved().offline_id).toBe(id) // no debounce: saved before the queue write
		expect(saved()).toHaveProperty("idempotency_key") // F5's online key goes here
		expect(await cart.checkoutOfflineId()).toBe(id)

		const next = freshCart()
		await next.restoreOpenCart(SCOPE)
		expect(await next.checkoutOfflineId()).toBe(id)
		next.clearCart({ returnSerials: false })
		expect(await next.checkoutOfflineId()).not.toBe(id)
	})

	it("I2 (e): each tab restores only its own cart; a new tab starts empty", async () => {
		await pricedCart() // tab-1: ITEM_A × 1
		sessionStorage.setItem(OPEN_CART_TAB_KEY, "tab-2")
		const tab2 = freshCart()
		expect(await tab2.restoreOpenCart(SCOPE)).toBe(false)
		expect(tab2.invoiceItems).toHaveLength(0)
		tab2.customer = CUSTOMER
		tab2.addItem(ITEM_A, 3)
		await vi.waitFor(() => expect(saved()?.items?.[0]?.quantity).toBe(3), { timeout: 2000 })

		sessionStorage.setItem(OPEN_CART_TAB_KEY, "tab-1")
		const tab1 = freshCart()
		expect(await tab1.restoreOpenCart(SCOPE)).toBe(true)
		expect(paidLine(tab1).quantity).toBe(1)

		sessionStorage.setItem(OPEN_CART_TAB_KEY, "tab-2")
		const tab2Again = freshCart()
		expect(await tab2Again.restoreOpenCart(SCOPE)).toBe(true)
		expect(paidLine(tab2Again).quantity).toBe(3)
	})

	it("I2 (e): shift close and logout forget every tab's cart", async () => {
		await pricedCart()
		sessionStorage.setItem(OPEN_CART_TAB_KEY, "tab-2")
		const cart = await pricedCart()
		expect(storage.rows.size).toBe(2)
		await cart.stopCartPersistence()
		expect(storage.rows.size).toBe(0)
	})

	it("saves a cart with a customer and no items, and restores the customer", async () => {
		const cart = freshCart()
		await cart.restoreOpenCart(SCOPE)
		cart.customer = CUSTOMER
		await vi.waitFor(() => expect(saved()?.customer).toBe(CUSTOMER), { timeout: 2000 })
		const next = freshCart()
		expect(await next.restoreOpenCart(SCOPE)).toBe(true)
		expect(next.customer).toBe(CUSTOMER)
		expect(next.invoiceItems).toHaveLength(0)
	})

	it("a storage call that never settles does not hang the restore or the shift close", async () => {
		storage.broken = "hang"
		const cart = freshCart()
		const started = Date.now()
		expect(await cart.restoreOpenCart(SCOPE)).toBe(false)
		await cart.stopCartPersistence()
		expect(Date.now() - started).toBeLessThan(6000)
	}, 10000)

	for (const mode of ["throw", "reject"]) {
		it(`works as today when storage fails (${mode})`, async () => {
			storage.broken = mode
			const cart = freshCart()
			expect(await cart.restoreOpenCart(SCOPE)).toBe(false)
			cart.customer = CUSTOMER
			cart.addItem(ITEM_A)
			await settle(cart, 0)
			expect(isFnfLine(paidLine(cart))).toBe(true)
			await wait(600)
			cart.clearCart()
			await cart.stopCartPersistence()
			expect(cart.invoiceItems).toHaveLength(0)
		})
	}
})
