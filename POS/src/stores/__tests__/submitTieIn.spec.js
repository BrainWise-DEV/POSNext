/**
 * F6: F5's idempotent submit tied into F4's saved cart (Rulings 138, 144).
 * A restored cart whose submit was in flight re-sends it with the same key.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
	return {
		calls: [],
		updates: [],
		submits: [],
		byKey: new Map(),
		loseNext: false,
		dropNext: false,
		seq: 0,
		slotAtSubmit: [],
		checkFails: false,
		checkSynced: undefined,
		checkInFlight: false,
	}
})
// The offline `settings` table, in memory.
const storage = vi.hoisted(() => ({ rows: new Map(), queue: [] }))
const toast = vi.hoisted(() => ({ messages: [] }))

const clone = (value) => JSON.parse(JSON.stringify(value))

vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: ({ url } = {}) => ({
		submit: vi.fn(async (params) => {
			if (String(url).endsWith("invoices.update_invoice")) {
				server.updates.push(clone(params.data))
				return { name: "SINV-CHECK", grand_total: 50 }
			}
			if (String(url).endsWith("invoices.submit_invoice")) {
				server.submits.push(clone(params))
				server.slotAtSubmit.push(clone([...storage.rows.values()][0]?.value?.pending_submit || null))
				if (server.dropNext) {
					// The request never reached the server: nothing was made.
					server.dropNext = false
					throw new TypeError("Failed to fetch")
				}
				const key = params.data?.idempotency_key
				let result = key && server.byKey.get(key)
				if (!result) {
					server.seq += 1
					result = { name: `SINV-${server.seq}`, grand_total: 50 }
					if (key) server.byKey.set(key, result)
				}
				if (server.loseNext) {
					server.loseNext = false
					throw new TypeError("Failed to fetch")
				}
				return { ...result }
			}
			if (String(url).endsWith("pos_profile.get_taxes")) return []
			if (String(url).includes("apply_offers")) server.calls.push({ method: "apply_offers" })
			return { items: [], free_items: [], applied_pricing_rules: [], discount_amount: 0 }
		}),
		reload: vi.fn(),
		fetch: vi.fn(),
	}),
}))
vi.mock("@/utils/apiWrapper", () => ({
	call: vi.fn(async (method, params) => {
		server.calls.push({ method, params: clone(params || {}) })
		if (String(method).endsWith("check_offline_invoice_synced")) {
			if (server.checkFails) throw new TypeError("Failed to fetch")
			if (server.checkInFlight) return { synced: false, sales_invoice: null, status: "Pending", in_flight: true }
			if (server.checkSynced === false) return { synced: false, sales_invoice: null }
			const made = server.byKey.get(String(params.offline_id).replace(/^pos_online:(SO:)?/, ""))
			return { synced: Boolean(made), sales_invoice: made?.name || null }
		}
		return []
	}),
}))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({
		showSuccess: (message) => toast.messages.push(message),
		showError: vi.fn(),
		showWarning: (message) => toast.messages.push(message),
		showInfo: (message) => toast.messages.push(message),
	}),
}))
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }))
vi.mock("@/utils/offline/db", () => ({
	db: {
		settings: {
			get: async (key) => (storage.rows.has(key) ? clone(storage.rows.get(key)) : undefined),
			put: async (row) => {
				storage.rows.set(row.key, clone(row))
			},
			delete: async (key) => {
				storage.rows.delete(key)
			},
			toArray: async () => [...storage.rows.values()].map(clone),
			bulkDelete: async (keys) => {
				for (const key of keys) storage.rows.delete(key)
			},
		},
		// The offline invoice queue (indexed on offline_id).
		invoice_queue: {
			where: (field) => ({
				equals: (value) => ({
					first: async () => storage.queue.find((row) => row[field] === value),
				}),
			}),
		},
	},
	getOneTimeRedemptions: async () => [],
	setOneTimeRedemptions: async () => {},
	addOneTimeRedemptions: async () => {},
}))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("../posCart")
const { usePOSOffersStore } = await import("../posOffers")
const { usePaymentOpenCheck } = await import("@/composables/usePaymentOpenCheck")
const { offlineState } = await import("@/utils/offline/offlineState")
const { OPEN_CART_TAB_KEY, openCartSlotKey, resetOpenCartStorage } = await import("@/utils/offline/openCart")

const SCOPE = { user: "cashier-a@example.com", pos_profile: "POS-1", pos_opening_shift: "POS-OPEN-1" }
const ITEM = {
	item_code: "A",
	item_name: "A",
	rate: 50,
	price_list_rate: 50,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
}
const AUTO_OFFER = {
	name: "RULE-A10",
	title: "A 10%",
	apply_on: "Item Code",
	offer: "Item Price",
	auto: 1,
	coupon_based: 0,
	min_qty: 1,
	max_qty: 0,
	min_amt: 0,
	max_amt: 0,
	discount_type: "Discount Percentage",
	discount_percentage: 10,
	eligible_items: ["A"],
	eligible_item_groups: [],
	eligible_brands: [],
}
const PAYMENT = { payments: [{ mode_of_payment: "Cash", amount: 50 }], change_amount: 0 }

const keys = () => server.submits.map((s) => s.data.idempotency_key)
const saved = () => storage.rows.get(openCartSlotKey())?.value || null

/** A fresh Pinia: what the page has after F5. */
function freshCart() {
	setActivePinia(createPinia())
	const cart = usePOSCartStore()
	cart.posProfile = SCOPE.pos_profile
	cart.posOpeningShift = SCOPE.pos_opening_shift
	return cart
}

/** CUST-1 with item A, saved for SCOPE, paid as POSSale does before the submit. */
async function savedCart() {
	const cart = freshCart()
	expect(await cart.restoreOpenCart(SCOPE)).toBe(false)
	cart.customer = "CUST-1"
	cart.addItem({ ...ITEM })
	cart.payments = clone(PAYMENT.payments)
	cart.lastOnlinePayment = clone(PAYMENT)
	await vi.waitFor(() => expect(saved()?.items?.length).toBe(1), { timeout: 2000 })
	return cart
}

/** Run `action`; when the "same sale?" dialog opens, answer `choice` ("same", "new", or null: closed). */
async function decide(cart, choice, action) {
	const running = action()
	await vi.waitFor(() => expect(cart.submitDecision).toBeTruthy())
	cart.decideSubmit(choice)
	return running
}

describe("F6 tie-in: the saved cart carries the submit key", () => {
	beforeEach(() => {
		Object.assign(server, {
			calls: [],
			updates: [],
			submits: [],
			byKey: new Map(),
			loseNext: false,
			dropNext: false,
			seq: 0,
			slotAtSubmit: [],
			checkFails: false,
			checkSynced: undefined,
			checkInFlight: false,
		})
		storage.rows = new Map()
		storage.queue = []
		toast.messages.length = 0
		sessionStorage.setItem(OPEN_CART_TAB_KEY, "tab-1")
		resetOpenCartStorage()
		vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(false)
	})
	afterEach(() => {
		vi.restoreAllMocks()
	})

	it("item 1: the key is in the slot before the request goes out", async () => {
		const cart = await savedCart()
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow("Failed to fetch")
		expect(server.slotAtSubmit[0]).toMatchObject({ key: keys()[0], unresolved: true })
		expect(saved().idempotency_key).toBe(keys()[0])
	})

	it("item 1: a restored cart whose submit was in flight re-sends the same key and gets that sale", async () => {
		const cart = await savedCart()
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow("Failed to fetch")

		const next = freshCart()
		expect(await next.restoreOpenCart(SCOPE)).toBe(true)
		expect(next.hasUnresolvedSubmit()).toBe(true)
		// POSSale's resume re-sends the last payment: it survives the reload too.
		expect(next.lastOnlinePayment).toEqual(PAYMENT)
		// Ruling 149: the very cart, restored: no gate, the same key, the server's sale.
		const result = await next.submitInvoice()
		expect(result.name).toBe("SINV-1")
		expect(keys()).toHaveLength(2)
		expect(keys()[1]).toBe(keys()[0])
		expect(server.seq).toBe(1)
	})

	it("item 1: a restored cart with an unanswered submit is not re-priced (its hash would change)", async () => {
		const cart = await savedCart()
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow("Failed to fetch")
		server.calls = []

		const next = freshCart()
		// An auto offer on A: a re-price asks apply_offers.
		usePOSOffersStore().setAvailableOffers([AUTO_OFFER])
		expect(await next.restoreOpenCart(SCOPE)).toBe(true)
		await new Promise((resolve) => setTimeout(resolve, 400))
		const methods = server.calls.map((c) => c.method)
		expect(methods).not.toContain("apply_offers")
		expect(methods.filter((m) => m.endsWith("get_customer_one_time_redemptions"))).toEqual([])
		expect(next.hasUnresolvedSubmit()).toBe(true)
	})

	it("item 1: an answered sale leaves no key in the slot", async () => {
		const cart = await savedCart()
		expect((await cart.submitInvoice()).name).toBe("SINV-1")
		cart.clearCart({ returnSerials: false })
		await vi.waitFor(() => expect(saved()).toBeNull())
	})

	it("item 2: a Sales Order submit carries a key; a retry after a lost response returns the first order", async () => {
		const cart = await savedCart()
		cart.setTargetDoctype("Sales Order")
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow("Failed to fetch")
		expect(keys()[0]).toMatch(/^[A-Za-z0-9_-]{8,100}$/)
		expect(cart.hasUnresolvedSubmit()).toBe(true)
		const result = await cart.submitInvoice()
		expect(result.name).toBe("SINV-1")
		expect(keys()[1]).toBe(keys()[0])
		expect(server.seq).toBe(1)
		// The retry makes no second order draft: it goes straight to the keyed submit.
		expect(server.updates).toHaveLength(1)
	})

	it("item 2: a restored Sales Order cart whose submit was in flight re-sends its key", async () => {
		const cart = await savedCart()
		cart.setTargetDoctype("Sales Order")
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow("Failed to fetch")

		const next = freshCart()
		expect(await next.restoreOpenCart(SCOPE)).toBe(true)
		expect(next.targetDoctype).toBe("Sales Order")
		expect(next.hasUnresolvedSubmit()).toBe(true)
		expect((await next.submitInvoice()).name).toBe("SINV-1")
		expect(keys()[1]).toBe(keys()[0])
		expect(server.seq).toBe(1)
	})

	it("item 2: an order key is asked about under the order prefix", async () => {
		const cart = await savedCart()
		cart.setTargetDoctype("Sales Order")
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow("Failed to fetch")
		await cart.clearCart()
		await cart.resolvePendingSubmit()
		const checks = server.calls.filter((c) => c.method.endsWith("check_offline_invoice_synced"))
		expect(checks.map((c) => c.params.offline_id)).toEqual([`pos_online:SO:${keys()[0]}`])
	})

	it("item 2: the same cart as an invoice and as an order are different attempts", async () => {
		const cart = await savedCart()
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow("Failed to fetch")
		cart.setTargetDoctype("Sales Order")
		expect(cart.hasUnresolvedSubmit()).toBe(false)
		server.checkSynced = false // the server says that invoice was not made
		await cart.submitInvoice()
		expect(keys()[1]).toBeTruthy()
		expect(keys()[1]).not.toBe(keys()[0])
	})

	it("item 4: a restored cart whose offline sale is already queued is closed, never paid again", async () => {
		const cart = await savedCart()
		const id = await cart.checkoutOfflineId()
		// The queue write landed; the crash came before the cart was cleared.
		storage.queue.push({ id: 7, offline_id: id, synced: false, data: { offline_id: id } })

		const next = freshCart()
		expect(await next.restoreOpenCart(SCOPE)).toBe(false)
		expect(next.invoiceItems).toHaveLength(0)
		expect(next.alreadyQueuedSale).toEqual({ offline_id: id })
		await vi.waitFor(() => expect(saved()).toBeNull())
		expect(server.submits).toHaveLength(0)
	})

	it("item 4: a synced row still in the queue counts as queued too", async () => {
		const cart = await savedCart()
		const id = await cart.checkoutOfflineId()
		storage.queue.push({ id: 8, offline_id: id, synced: true, data: { offline_id: id } })
		const next = freshCart()
		expect(await next.restoreOpenCart(SCOPE)).toBe(false)
		expect(next.alreadyQueuedSale?.offline_id).toBe(id)
	})

	it("item 4: a cart whose offline_id never reached the queue is restored", async () => {
		const cart = await savedCart()
		await cart.checkoutOfflineId()
		const next = freshCart()
		expect(await next.restoreOpenCart(SCOPE)).toBe(true)
		expect(next.invoiceItems).toHaveLength(1)
		expect(next.alreadyQueuedSale).toBeNull()
	})

	/** A response lost while the POS stays online, then Clear Cart, then the same cart rung again. */
	async function lostThenClearedThenRungAgain() {
		const cart = await savedCart()
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow("Failed to fetch")
		await cart.clearCart()
		cart.customer = "CUST-1"
		cart.addItem({ ...ITEM })
		cart.payments = clone(PAYMENT.payments)
		return cart
	}

	it("item 5 (F-1): Checkout of the identical cart after Clear Cart opens payment, it does not resume the old sale", async () => {
		const cart = await lostThenClearedThenRungAgain()
		// A cleared sale is not "this cart's unanswered submit": not resumed, not frozen.
		expect(cart.hasUnresolvedSubmit()).toBe(false)
		const resumed = vi.fn(async () => cart.submitInvoice())
		const openPayment = vi.fn()
		// As POSSale wires it.
		const check = usePaymentOpenCheck({
			isOffline: () => false,
			checkPrice: () => cart.checkPriceBeforePayment(),
			openPayment,
			showError: vi.fn(),
			resumeUnresolved: () => (cart.lastOnlinePayment && cart.hasUnresolvedSubmit() ? resumed() : null),
		})
		expect(await check.requestPayment()).toBe(true)
		expect(resumed).not.toHaveBeenCalled()
		expect(openPayment).toHaveBeenCalledTimes(1)
	})

	// ── Ruling 146: when the outcome is ambiguous, the cashier decides ─────────

	const checks = () => server.calls.filter((c) => c.method.endsWith("check_offline_invoice_synced"))

	/** A response lost online, the cart left on screen (or cleared, then rung again). */
	async function lost({ doctype = "Sales Invoice", cleared = false, edited = false } = {}) {
		const cart = await savedCart()
		if (doctype !== "Sales Invoice") cart.setTargetDoctype(doctype)
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow("Failed to fetch")
		if (cleared) {
			await cart.clearCart() // the target goes back to Sales Invoice; the cashier picks it again
			if (doctype !== "Sales Invoice") cart.setTargetDoctype(doctype)
			cart.customer = "CUST-1"
			cart.addItem({ ...ITEM })
			cart.payments = clone(PAYMENT.payments)
		}
		if (edited) cart.updateItemQuantity("A", 2)
		return cart
	}

	for (const doctype of ["Sales Invoice", "Sales Order"]) {
		const prefix = doctype === "Sales Order" ? "pos_online:SO:" : "pos_online:"

		// The cart on screen, unchanged, skips the gate (Ruling 149): see below.
		for (const cleared of [true]) {
			const label = `${doctype}, ${cleared ? "after Clear Cart" : "cart on screen"}`

			it(`146 (a) ${label}: the server says it was made: the submit stops, the cashier is told, the cart stays`, async () => {
				const cart = await lost({ doctype, cleared })
				const result = await cart.submitInvoice()
				expect(result).toEqual({ stopped: true })
				expect(checks().map((c) => c.params.offline_id)).toEqual([`${prefix}${keys()[0]}`])
				expect(cart.madeSaleNotice).toBe("SINV-1")
				expect(server.seq).toBe(1)
				expect(keys()).toHaveLength(1) // no submit in the same click
				expect(cart.invoiceItems).toHaveLength(1)
				// A second press is a new sale with a new key.
				cart.dismissMadeSaleNotice()
				const again = await cart.submitInvoice()
				expect(again.name).toBe("SINV-2")
				expect(keys()[1]).not.toBe(keys()[0])
			})

			it(`146 (a) ${label}: the server says it was not made: the key is dropped and the sale goes through`, async () => {
				const cart = await savedCart()
				if (doctype !== "Sales Invoice") cart.setTargetDoctype(doctype)
				server.dropNext = true
				await expect(cart.submitInvoice()).rejects.toThrow("Failed to fetch")
				if (cleared) {
					await cart.clearCart()
					if (doctype !== "Sales Invoice") cart.setTargetDoctype(doctype)
					cart.customer = "CUST-1"
					cart.addItem({ ...ITEM })
				}
				const result = await cart.submitInvoice()
				expect(result.name).toBe("SINV-1")
				expect(checks()).toHaveLength(1)
				expect(keys()[1]).not.toBe(keys()[0])
				expect(cart.submitDecision).toBeNull()
			})

			for (const choice of ["same", "new"]) {
				it(`146 (b) ${label}, identical cart, no answer, the cashier says "${choice}"`, async () => {
					const cart = await lost({ doctype, cleared })
					server.checkFails = true
					const result = await decide(cart, choice, () => cart.submitInvoice())
					expect(cart.submitDecision).toBeNull()
					if (choice === "same") {
						expect(result.name).toBe("SINV-1")
						expect(keys()[1]).toBe(keys()[0])
						expect(server.seq).toBe(1)
					} else {
						expect(result.name).toBe("SINV-2")
						expect(keys()[1]).not.toBe(keys()[0])
					}
				})

				it(`146 (b) ${label}, offline, identical cart: the cashier says "${choice}"`, async () => {
					const cart = await lost({ doctype, cleared })
					vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(true)
					const gate = await decide(cart, choice, () => cart.settlePendingSubmit({ offline: true }))
					expect(checks()).toEqual([]) // offline: no check
					if (choice === "same") {
						// The queued sale carries the key and its doctype: the sync dedups (146 (c)).
						expect(gate).toEqual({ proceed: true, carry: { key: keys()[0], doctype } })
					} else {
						expect(gate).toEqual({ proceed: true, carry: null })
					}
				})
			}
		}

		for (const choice of ["same", "new"]) {
			it(`146 (b) ${doctype}, edited cart, no answer: the cashier says "${choice}"`, async () => {
				const cart = await lost({ doctype, edited: true })
				server.checkFails = true
				const result = await decide(cart, choice, () => cart.submitInvoice())
				if (choice === "same") {
					expect(result.name).toBe("SINV-1")
					expect(keys()[1]).toBe(keys()[0])
				} else {
					expect(result.name).toBe("SINV-2")
					expect(keys()[1]).not.toBe(keys()[0])
				}
			})

			it(`146 (b) ${doctype}, offline, edited cart: the cashier decides ("${choice}"), never blocked or silent`, async () => {
				const cart = await lost({ doctype, edited: true })
				vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(true)
				const gate = await decide(cart, choice, () => cart.settlePendingSubmit({ offline: true }))
				expect(gate.proceed).toBe(true)
				expect(gate.carry).toEqual(choice === "same" ? { key: keys()[0], doctype } : null)
			})
		}

		it(`146 (b) ${doctype}: closing the decision dialog stops the submit`, async () => {
			const cart = await lost({ doctype, edited: true })
			server.checkFails = true
			const result = await decide(cart, null, () => cart.submitInvoice())
			expect(result).toEqual({ stopped: true })
			expect(keys()).toHaveLength(1)
		})

		it(`146 (d) ${doctype}: a cleared key survives a reload; the identical sale after it is told, not made twice`, async () => {
			const cart = await lost({ doctype })
			await cart.clearCart()
			await vi.waitFor(() => expect(saved()?.pending_submit?.cleared).toBe(true))

			const next = freshCart()
			expect(await next.restoreOpenCart(SCOPE)).toBe(false) // no cart, only the key
			expect(next.pendingSubmit?.key).toBe(keys()[0])
			if (doctype !== "Sales Invoice") next.setTargetDoctype(doctype)
			next.customer = "CUST-1"
			next.addItem({ ...ITEM })
			expect(await next.submitInvoice()).toEqual({ stopped: true })
			expect(next.madeSaleNotice).toBe("SINV-1")
			expect(server.seq).toBe(1)
		})
	}

	// ── Ruling 149: the very cart on screen re-sends its key; the gate is for cleared or edited carts ──

	for (const doctype of ["Sales Invoice", "Sales Order"]) {
		it(`149 P1 ${doctype}: a retry while the first submit is still running makes one sale`, async () => {
			const cart = await lost({ doctype })
			// Still running on the server: a check would answer "not synced".
			server.checkSynced = false
			const result = await cart.submitInvoice()
			expect(result.name).toBe("SINV-1")
			expect(keys()[1]).toBe(keys()[0])
			expect(server.seq).toBe(1)
			expect(checks()).toEqual([])
		})

		it(`149 P2 ${doctype}: the sold cart, retried, closes as SINV-1; no second Checkout is left`, async () => {
			const cart = await lost({ doctype })
			const result = await cart.submitInvoice()
			expect(result.name).toBe("SINV-1")
			expect(result.stopped).toBeUndefined()
			expect(cart.madeSaleNotice).toBeNull()
			// The normal success path: the cart is empty and holds no key.
			expect(cart.invoiceItems).toHaveLength(0)
			expect(cart.pendingSubmit).toBeNull()
			expect(server.seq).toBe(1)
		})

		it(`149 P3 ${doctype}: the resume after a reload closes as SINV-1`, async () => {
			await lost({ doctype })
			const next = freshCart()
			expect(await next.restoreOpenCart(SCOPE)).toBe(true)
			const result = await next.submitInvoice()
			expect(result.name).toBe("SINV-1")
			expect(next.invoiceItems).toHaveLength(0)
			expect(server.seq).toBe(1)
			expect(checks()).toEqual([])
		})

		it(`149 ${doctype}: offline, the very cart carries its key without asking`, async () => {
			const cart = await lost({ doctype })
			const gate = await cart.settlePendingSubmit({ offline: true })
			expect(gate).toEqual({ proceed: true, carry: { key: keys()[0], doctype } })
			expect(cart.submitDecision).toBeNull()
		})

		it(`149 ${doctype}: an edited cart while the first submit is in flight is asked about, never sold silently`, async () => {
			const cart = await lost({ doctype, edited: true })
			server.checkInFlight = true
			const result = await decide(cart, "same", () => cart.submitInvoice())
			expect(checks()).toHaveLength(1)
			expect(result.name).toBe("SINV-1")
			expect(keys()[1]).toBe(keys()[0])
			expect(server.seq).toBe(1)
		})

		it(`149 ${doctype}: a cleared identical cart while the first submit is in flight is asked about`, async () => {
			const cart = await lost({ doctype, cleared: true })
			server.checkInFlight = true
			const result = await decide(cart, "new", () => cart.submitInvoice())
			expect(result.name).toBe("SINV-2")
			expect(cart.madeSaleNotice).toBeNull()
		})
	}

	it("146: a different sale after Clear Cart, with no answer, is not asked about", async () => {
		const cart = await lost({ cleared: false })
		await cart.clearCart()
		cart.customer = "CUST-1"
		cart.addItem({ ...ITEM, item_code: "B", item_name: "B" })
		server.checkFails = true
		const result = await cart.submitInvoice()
		expect(result.name).toBe("SINV-2")
		expect(cart.submitDecision).toBeNull()
	})

	it("146: a cart closed as already submitted forgets its key (no second notice for the same sale)", async () => {
		const cart = await lost()
		cart.closeAsAlreadySubmitted({ name: "SINV-1", grand_total: 50 })
		expect(cart.pendingSubmit).toBeNull()
	})
})
