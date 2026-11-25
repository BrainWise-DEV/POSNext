/**
 * A lost submit response never makes a second sale (UI test D-19).
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
	return { updates: [], submits: [], byKey: new Map(), loseNext: false, refuseNext: null, seq: 0, checks: [], checkFails: false }
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async (method, args) => {
		if (String(method).endsWith("check_offline_invoice_synced")) {
			server.checks.push(args.offline_id)
			if (server.checkFails) throw new TypeError("Failed to fetch")
			if (server.checkSynced === false) return { synced: false, sales_invoice: null }
			const made = server.byKey.get(String(args.offline_id).replace(/^pos_online:/, ""))
			return { synced: Boolean(made), sales_invoice: made?.name || null }
		}
		return {}
	}),
	createResource: ({ url } = {}) => {
		const submit = vi.fn(async (params) => {
			if (String(url).endsWith("invoices.update_invoice")) {
				server.updates.push(JSON.parse(JSON.stringify(params.data)))
				return { name: "SINV-CHECK", grand_total: 50 }
			}
			if (String(url).endsWith("invoices.submit_invoice")) {
				server.submits.push(JSON.parse(JSON.stringify(params)))
				if (server.refuseNext) {
					const error = server.refuseNext
					server.refuseNext = null
					throw error
				}
				// The server's idempotency: one invoice per key.
				const key = params.data?.idempotency_key
				let result = key && server.byKey.get(key)
				if (!result) {
					server.seq += 1
					result = { name: `SINV-${server.seq}`, grand_total: 50 }
					if (key) server.byKey.set(key, result)
				}
				if (server.loseNext) {
					// Submitted on the server; the response never reaches the browser.
					server.loseNext = false
					throw new TypeError("Failed to fetch")
				}
				return { ...result }
			}
			if (String(url).endsWith("pos_profile.get_taxes")) return []
			return { items: [], free_items: [], applied_pricing_rules: [], discount_amount: 0 }
		})
		return { submit, reload: vi.fn(), fetch: vi.fn() }
	},
}))
const toast = vi.hoisted(() => ({ messages: [] }))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({
		showSuccess: (message) => toast.messages.push(message),
		showError: vi.fn(),
		showWarning: vi.fn(),
		showInfo: (message) => toast.messages.push(message),
	}),
}))
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("@/stores/posCart")
const { usePaymentOpenCheck } = await import("@/composables/usePaymentOpenCheck")
const { cleanupUserSession } = await import("@/utils/sessionCleanup")
const { offlineState } = await import("@/utils/offline/offlineState")

const item = {
	item_code: "A",
	item_name: "A",
	rate: 50,
	price_list_rate: 50,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
}

const keys = () => server.submits.map((s) => s.data.idempotency_key)

/** The key this very cart carries (its pending submit's, when the cart is unchanged), else null. */
const keyFor = (cart) =>
	cart.pendingSubmit && cart.pendingMatchesCart("Sales Invoice") ? cart.pendingSubmit.key : null

/** Offline, does the checkout ask the cashier "is this the same sale?" (Rulings 146, 149)? */
async function offlineAsks(cart) {
	const running = cart.settlePendingSubmit({ offline: true })
	const asked = Boolean(cart.submitDecision)
	if (asked) cart.decideSubmit(null)
	await running
	return asked
}

describe("online submit idempotency", () => {
	let cart

	beforeEach(() => {
		setActivePinia(createPinia())
		Object.assign(server, {
			updates: [],
			submits: [],
			byKey: new Map(),
			loseNext: false,
			refuseNext: null,
			seq: 0,
			checks: [],
			checkFails: false,
			checkSynced: undefined,
		})
		toast.messages.length = 0
		// Online throughout, as POSSale's online branch is (the real flag follows timers).
		vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(false)
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = "CUST-1"
		cart.addItem({ ...item })
		cart.payments = [{ mode_of_payment: "Cash", amount: 50 }]
	})

	it("every online submit carries a key", async () => {
		await cart.submitInvoice()
		expect(keys()).toHaveLength(1)
		expect(keys()[0]).toMatch(/^[A-Za-z0-9_-]{8,100}$/)
	})

	it("a retry after a lost response sends the same key and gets the first invoice", async () => {
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow("Failed to fetch")
		expect(cart.invoiceItems).toHaveLength(1)
		expect(cart.hasUnresolvedSubmit()).toBe(true)

		// Ruling 149: the very cart, retried: no gate, the same key, the server's sale.
		const result = await cart.submitInvoice()
		expect(result.name).toBe("SINV-1")
		expect(server.checks).toEqual([])
		expect(keys()).toHaveLength(2)
		expect(keys()[1]).toBe(keys()[0])
		expect(server.seq).toBe(1)
		expect(cart.hasUnresolvedSubmit()).toBe(false)
	})

	it("the next sale gets a new key", async () => {
		await cart.submitInvoice()
		cart.addItem({ ...item })
		cart.payments = [{ mode_of_payment: "Cash", amount: 50 }]
		await cart.submitInvoice()
		expect(keys()[1]).not.toBe(keys()[0])
	})

	it("a changed cart after a lost response is a new attempt", async () => {
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		cart.addItem({ ...item, item_code: "B", item_name: "B" })
		expect(cart.hasUnresolvedSubmit()).toBe(false)
		await cart.submitInvoice().catch(() => {})
		expect(keys()[1]).not.toBe(keys()[0])
	})

	it("a refusal the server answered is not left unresolved", async () => {
		server.refuseNext = Object.assign(new Error("refused"), { exc_type: "ValidationError" })
		await expect(cart.submitInvoice()).rejects.toThrow("refused")
		expect(cart.hasUnresolvedSubmit()).toBe(false)
	})

	it("Checkout after a lost response re-sends the submit instead of a new price check", async () => {
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		const resumed = vi.fn(async () => cart.submitInvoice())
		const openPayment = vi.fn()
		const check = usePaymentOpenCheck({
			isOffline: () => false,
			checkPrice: () => cart.checkPriceBeforePayment(),
			openPayment,
			showError: vi.fn(),
			resumeUnresolved: () => (cart.hasUnresolvedSubmit() ? resumed() : null),
		})
		expect(await check.requestPayment()).toBe(true)
		expect(resumed).toHaveBeenCalledTimes(1)
		expect(server.updates).toHaveLength(0)
		expect(openPayment).not.toHaveBeenCalled()
		expect(server.seq).toBe(1)
	})

	it("the same cart queued offline after a lost response carries its key (Ruling 139)", async () => {
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		expect(keyFor(cart)).toBe(keys()[0])
		expect(await offlineAsks(cart)).toBe(false)
	})

	it("a changed cart after a lost response cannot carry the key: offline checkout is blocked", async () => {
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		cart.addItem({ ...item, item_code: "B", item_name: "B" })
		expect(keyFor(cart)).toBeNull()
		expect(await offlineAsks(cart)).toBe(true)
	})

	it("no online attempt: no key and nothing blocked", async () => {
		expect(keyFor(cart)).toBeNull()
		expect(await offlineAsks(cart)).toBe(false)
	})

	it("offline, a blocked checkout never opens payment", async () => {
		const openPayment = vi.fn()
		const showError = vi.fn()
		const check = usePaymentOpenCheck({
			isOffline: () => true,
			checkPrice: vi.fn(),
			openPayment,
			showError,
			offlineBlocked: () => "The last sale may already be saved. Reconnect to confirm.",
		})
		expect(await check.requestPayment()).toBe(false)
		expect(openPayment).not.toHaveBeenCalled()
		expect(showError).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining("Reconnect") }))
	})

	it("Ruling 141: after Clear Cart, a new offline sale goes through", async () => {
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		await cart.clearCart()
		cart.addItem({ ...item, item_code: "B", item_name: "B" })
		expect(await offlineAsks(cart)).toBe(false)
		expect(keyFor(cart)).toBeNull()
	})

	it("Ruling 141: an edited re-entry of the unanswered cart (not cleared) is blocked", async () => {
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		cart.updateItemQuantity(cart.invoiceItems[0].item_code, 2)
		expect(await offlineAsks(cart)).toBe(true)
	})

	it("Ruling 141/146: an exact re-entry after Clear Cart matches the key; offline the cashier is asked", async () => {
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		await cart.clearCart()
		cart.customer = "CUST-1"
		cart.addItem({ ...item })
		expect(keyFor(cart)).toBe(keys()[0])
		// A cleared cart rung again may be a new sale: the cashier decides (Ruling 146 (b)).
		expect(await offlineAsks(cart)).toBe(true)
	})

	it("Ruling 143: a sale the server made is told once, then its key is dropped", async () => {
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		await cart.clearCart()
		// No answer: the key is kept and nothing is said.
		server.checkFails = true
		await cart.resolvePendingSubmit()
		expect(toast.messages).toEqual([])
		expect(cart.madeSaleNotice).toBeNull()
		cart.customer = "CUST-1"
		cart.addItem({ ...item })
		expect(keyFor(cart)).toBe(keys()[0])
		await cart.clearCart()
		server.checkFails = false
		await cart.resolvePendingSubmit()
		expect(server.checks.at(-1)).toBe(`pos_online:${keys()[0]}`)
		// A dialog the cashier must dismiss (F6, Ruling 144), not a toast.
		expect(cart.madeSaleNotice).toBe("SINV-1")
		expect(toast.messages).toEqual([])
		cart.dismissMadeSaleNotice()
		expect(cart.madeSaleNotice).toBeNull()
		await cart.resolvePendingSubmit()
		expect(cart.madeSaleNotice).toBeNull()
		cart.customer = "CUST-1"
		cart.addItem({ ...item })
		expect(keyFor(cart)).toBeNull()
	})

	it("Ruling 143: an identical next sale after that makes a new invoice", async () => {
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		await cart.clearCart()
		await cart.resolvePendingSubmit()
		cart.customer = "CUST-1"
		cart.addItem({ ...item })
		cart.payments = [{ mode_of_payment: "Cash", amount: 50 }]
		expect((await cart.submitInvoice()).name).toBe("SINV-2")
		expect(keys()[1]).not.toBe(keys()[0])
		expect(server.seq).toBe(2)
	})

	it("Ruling 142: a sale the server did not make drops the key", async () => {
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		await cart.clearCart()
		server.checkSynced = false
		await cart.resolvePendingSubmit()
		cart.customer = "CUST-1"
		cart.addItem({ ...item })
		expect(keyFor(cart)).toBeNull()
		expect(toast.messages).toEqual([])
		expect(cart.madeSaleNotice).toBeNull()
	})

	it("on reconnect the key of a cart still on screen is kept (the resume re-sends it)", async () => {
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		await cart.resolvePendingSubmit()
		expect(cart.hasUnresolvedSubmit()).toBe(true)
		expect(keyFor(cart)).toBe(keys()[0])
	})

	it("the key is dropped on shift close and on logout", async () => {
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		cart.dropPendingSubmit()
		expect(keyFor(cart)).toBeNull()
		expect(cart.hasUnresolvedSubmit()).toBe(false)

		cart.customer = "CUST-1"
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		await cleanupUserSession()
		expect(cart.invoiceItems).toHaveLength(0)
		cart.customer = "CUST-1"
		cart.addItem({ ...item })
		expect(keyFor(cart)).toBeNull()
		expect(await offlineAsks(cart)).toBe(false)
	})

	it("the cart hash does not depend on row order", async () => {
		cart.addItem({ ...item, item_code: "B", item_name: "B" })
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		await cart.clearCart()
		cart.customer = "CUST-1"
		cart.addItem({ ...item, item_code: "B", item_name: "B" })
		cart.addItem({ ...item })
		expect(keyFor(cart)).toBe(keys()[0])
	})

	it("N-5: an answered online submit lifts the block", async () => {
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		await cart.clearCart()
		cart.customer = "CUST-1"
		cart.addItem({ ...item, item_code: "B", item_name: "B" })
		cart.payments = [{ mode_of_payment: "Cash", amount: 50 }]
		// Ruling 146 (a): the server says the last sale was made: told, this submit stops.
		expect(await cart.submitInvoice()).toEqual({ stopped: true })
		expect(cart.madeSaleNotice).toBe("SINV-1")
		expect((await cart.submitInvoice())?.name).toBeTruthy()
		cart.addItem({ ...item })
		expect(await offlineAsks(cart)).toBe(false)
	})

	it("a key handed to the queued offline sale no longer blocks", async () => {
		server.loseNext = true
		await expect(cart.submitInvoice()).rejects.toThrow()
		expect(keyFor(cart)).toBeTruthy()
		cart.releaseSubmitKey()
		await cart.clearCart()
		cart.addItem({ ...item })
		expect(await offlineAsks(cart)).toBe(false)
	})
})
