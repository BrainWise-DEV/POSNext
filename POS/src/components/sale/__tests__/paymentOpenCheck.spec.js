/**
 * Opening payment re-checks the price; a "Block submit" refusal never follows
 * payment (Task 8o, Ruling 101).
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
	return {
		updates: [],
		submits: [],
		draft: null,
		submitError: null,
		taxes: [],
		// A stored draft name the server no longer knows ("missing and not yours" share
		// one PermissionError).
		goneName: null,
	}
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: ({ url } = {}) => {
		const submit = vi.fn(async (params) => {
			const permissionError = () =>
				Object.assign(new Error("This document cannot be changed from this POS Profile."), {
					exc_type: "PermissionError",
				})
			if (String(url).endsWith("invoices.update_invoice")) {
				server.updates.push(JSON.parse(JSON.stringify(params.data)))
				if (server.goneName && params.data.name === server.goneName) throw permissionError()
				return { ...server.draft }
			}
			if (String(url).endsWith("invoices.submit_invoice")) {
				server.submits.push(JSON.parse(JSON.stringify(params)))
				if (server.goneName && params.invoice.name === server.goneName) throw permissionError()
				if (server.submitError) throw server.submitError
				return { name: params.invoice.name || "SINV-NEW", grand_total: 50 }
			}
			if (String(url).endsWith("pos_profile.get_taxes")) return server.taxes
			return { items: [], free_items: [], applied_pricing_rules: [], discount_amount: 0 }
		})
		return { submit, reload: vi.fn(), fetch: vi.fn() }
	},
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
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("@/stores/posCart")
const { usePaymentOpenCheck } = await import("@/composables/usePaymentOpenCheck")

const CAP_MESSAGE =
	"Friends & Family discount 15 on this invoice exceeds the customer's remaining monthly allowance"

const item = {
	item_code: "A",
	item_name: "A",
	rate: 50,
	price_list_rate: 50,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
}

/** The server's answer to the unpaid draft save: F&F capped to `fnf` off the 50 line. */
function draft(fnf) {
	return {
		name: "SINV-CHECK",
		grand_total: 50 - fnf,
		friends_and_family: {
			eligible: true,
			discount_percentage: 30,
			applied_count: fnf ? 1 : 0,
			items: [
				{
					idx: 0,
					applies: fnf > 0,
					discount_percentage: (fnf / 50) * 100,
					discount_amount: fnf,
					rate: 50 - fnf,
					capped: fnf < 15,
				},
			],
		},
	}
}

describe("payment-open price re-check", () => {
	let cart
	let openPayment
	let showError
	let check

	beforeEach(() => {
		setActivePinia(createPinia())
		Object.assign(server, {
			updates: [],
			submits: [],
			draft: null,
			submitError: null,
			taxes: [],
			goneName: null,
		})
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = "CUST-1"
		cart.addItem({ ...item })
		openPayment = vi.fn()
		showError = vi.fn()
		check = usePaymentOpenCheck({
			isOffline: () => false,
			checkPrice: () => cart.checkPriceBeforePayment(),
			openPayment,
			showError,
		})
	})

	it("opening payment re-checks and asks to confirm a changed total", async () => {
		expect(cart.grandTotal).toBe(50)
		server.draft = draft(15)

		expect(await check.requestPayment()).toBe(false)

		// The check is an unpaid draft save.
		expect(server.updates).toHaveLength(1)
		expect(server.updates[0].payments).toEqual([])
		expect(openPayment).not.toHaveBeenCalled()
		expect(check.pendingChange.value).toMatchObject({ previousTotal: 50, total: 35 })
		// The cart takes the server's F&F line, so the payment dialog asks for 35.
		expect(cart.grandTotal).toBe(35)

		check.confirmChange()
		expect(openPayment).toHaveBeenCalledTimes(1)
		expect(check.pendingChange.value).toBeNull()
	})

	it("unchanged total opens payment directly", async () => {
		server.draft = draft(0)

		expect(await check.requestPayment()).toBe(true)

		expect(server.updates).toHaveLength(1)
		expect(server.updates[0].payments).toEqual([])
		expect(openPayment).toHaveBeenCalledTimes(1)
		expect(check.pendingChange.value).toBeNull()
		expect(showError).not.toHaveBeenCalled()
	})

	it("submit cap refusal keeps the cart and re-runs the check", async () => {
		server.draft = draft(0)
		await check.requestPayment()
		expect(openPayment).toHaveBeenCalledTimes(1)

		cart.payments = [{ mode_of_payment: "Cash", amount: 50 }]
		server.submitError = Object.assign(new Error(CAP_MESSAGE), { exc_type: "ValidationError" })
		await expect(cart.submitInvoice()).rejects.toThrow(CAP_MESSAGE)

		// One request carried the payments: the submit of the checked draft.
		expect(server.submits).toHaveLength(1)
		expect(server.submits[0].invoice.name).toBe("SINV-CHECK")
		expect(server.submits[0].invoice.payments).toEqual([
			expect.objectContaining({ mode_of_payment: "Cash", amount: 50 }),
		])
		expect(server.updates.every((data) => data.payments.length === 0)).toBe(true)
		// The cart is kept.
		expect(cart.invoiceItems).toHaveLength(1)
		expect(cart.grandTotal).toBe(50)

		// The allowance went down meanwhile: the check runs again (unpaid) and asks.
		server.draft = draft(10)
		expect(await check.recheckAfterRefusal(CAP_MESSAGE)).toBe(true)
		expect(server.updates).toHaveLength(2)
		expect(server.updates[1]).toMatchObject({ name: "SINV-CHECK", payments: [] })
		expect(check.pendingChange.value).toMatchObject({
			previousTotal: 50,
			total: 40,
			message: CAP_MESSAGE,
		})
		expect(cart.grandTotal).toBe(40)
		expect(openPayment).toHaveBeenCalledTimes(1)
	})

	it("adopts the server's coupon and header, says why, and collects the server total", async () => {
		cart.applyDiscountToCart({ name: "C1", code: "C1", percentage: 0, amount: 1 })
		expect(cart.appliedCoupon?.code).toBe("C1")
		expect(cart.grandTotal).toBe(49)
		const reason = "Friends & Family saves more than coupon C1"
		server.draft = {
			name: "SINV-CHECK",
			grand_total: 50,
			discount_amount: 0,
			coupon_code: null,
			friends_and_family: {
				eligible: true,
				items: [],
				best_discount: { message: reason, message_en: reason },
			},
		}

		expect(await check.requestPayment()).toBe(false)

		expect(cart.appliedCoupon).toBeNull()
		expect(cart.additionalDiscount).toBe(0)
		expect(cart.grandTotal).toBe(50)
		expect(cart.paymentTotal).toBe(50)
		expect(check.pendingChange.value).toMatchObject({ previousTotal: 49, total: 50 })
		expect(check.pendingChange.value.message).toContain(reason)
		// The submit sends what the server checked: no coupon, no header.
		check.confirmChange()
		cart.payments = [{ mode_of_payment: "Cash", amount: 50 }]
		await cart.submitInvoice()
		expect(server.submits[0].invoice).toMatchObject({ coupon_code: null, discount_amount: 0 })
	})

	it("drift of a cent or two with tax and line discounts is adopted without a prompt", async () => {
		server.taxes = [{ charge_type: "On Net Total", rate: 14, account_head: "VAT" }]
		await cart.loadTaxRules("POS-1")
		cart.addItem({ ...item, item_code: "B", item_name: "B", rate: 33.33, price_list_rate: 33.33 })
		const line = cart.invoiceItems[1]
		line.quantity = 3
		line.discount_percentage = 7
		cart.recalculateItem(line)
		cart.rebuildIncrementalCache()
		const shown = cart.grandTotal
		const serverTotal = Math.round((shown + 0.02) * 100) / 100
		server.draft = { name: "SINV-CHECK", grand_total: serverTotal, discount_amount: 0 }

		expect(await check.requestPayment()).toBe(true)

		expect(check.pendingChange.value).toBeNull()
		expect(openPayment).toHaveBeenCalledTimes(1)
		expect(cart.paymentTotal).toBe(serverTotal)
	})

	it("a cleaned-up draft starts a new one without telling the cashier", async () => {
		server.draft = draft(0)
		await check.requestPayment()
		server.goneName = "SINV-CHECK"
		server.draft = { ...draft(0), name: "SINV-NEW-CHECK" }

		expect(await check.requestPayment()).toBe(true)
		expect(showError).not.toHaveBeenCalled()
		expect(server.updates.at(-1)).not.toHaveProperty("name")

		server.goneName = "SINV-NEW-CHECK"
		cart.payments = [{ mode_of_payment: "Cash", amount: 50 }]
		const result = await cart.submitInvoice()
		expect(result.name).toBe("SINV-NEW")
		expect(server.submits.at(-1).invoice).not.toHaveProperty("name")
	})

	it("a coupon that replaced F&F and is dropped gives its lines back as F&F", async () => {
		cart.invoiceItems[0].quantity = 3
		cart.recalculateItem(cart.invoiceItems[0])
		cart.rebuildIncrementalCache()
		cart.applyDiscountToCart({
			name: "C20",
			code: "C20",
			percentage: 0,
			amount: 20,
			suppress_friends_and_family: true,
		})
		expect(cart.fnfCouponOverride).not.toBeNull()
		expect(cart.grandTotal).toBe(130)
		server.draft = {
			name: "SINV-CHECK",
			grand_total: 105,
			discount_amount: 0,
			coupon_code: null,
			items: [
				{
					item_code: "A",
					is_free_item: 0,
					qty: 3,
					rate: 35,
					discount_percentage: 30,
					discount_amount: 15,
					posnext_discount_source: "friends_and_family",
				},
			],
			friends_and_family: {
				eligible: true,
				discount_percentage: 30,
				applied_count: 1,
				items: [{ idx: 0, applies: true, discount_percentage: 30, discount_amount: 45, rate: 35 }],
			},
		}

		await check.requestPayment()

		const line = cart.invoiceItems[0]
		expect(cart.fnfCouponOverride).toBeNull()
		expect(line.discount_source).toBe("friends_and_family")
		expect(cart.grandTotal).toBe(105)
		expect(cart.paymentTotal).toBe(105)
		check.confirmChange()
		cart.payments = [{ mode_of_payment: "Cash", amount: 105 }]
		await cart.submitInvoice()
		expect(server.submits[0].invoice.items[0]).toMatchObject({
			posnext_discount_source: "friends_and_family",
			discount_percentage: 30,
		})
	})

	it("an F&F row the block does not list is still stamped as F&F from the server row", async () => {
		server.draft = {
			name: "SINV-CHECK",
			grand_total: 35,
			discount_amount: 0,
			items: [
				{
					item_code: "A",
					is_free_item: 0,
					qty: 1,
					rate: 35,
					discount_percentage: 30,
					discount_amount: 15,
					posnext_discount_source: "friends_and_family",
				},
			],
		}

		await check.requestPayment()

		const line = cart.invoiceItems[0]
		expect(line.discount_source).toBe("friends_and_family")
		expect(cart.grandTotal).toBe(35)
		check.confirmChange()
		cart.payments = [{ mode_of_payment: "Cash", amount: 35 }]
		await cart.submitInvoice()
		expect(server.submits[0].invoice.items[0].posnext_discount_source).toBe("friends_and_family")
	})

	it("an offer the server removed is taken off the line", async () => {
		const line = cart.invoiceItems[0]
		line.discount_percentage = 10
		line.pricing_rules = ["R1"]
		cart.recalculateItem(line)
		cart.rebuildIncrementalCache()
		expect(cart.grandTotal).toBe(45)
		server.draft = {
			name: "SINV-CHECK",
			grand_total: 50,
			discount_amount: 0,
			items: [{ item_code: "A", is_free_item: 0, qty: 1, discount_amount: 0, discount_percentage: 0 }],
		}

		await check.requestPayment()

		expect(line.discount_amount).toBe(0)
		expect(line.pricing_rules).toEqual([])
		expect(cart.grandTotal).toBe(50)
		expect(check.pendingChange.value.message).toContain("A")
	})

	it("a synthesized free_qty row does not shift the F&F lines", async () => {
		cart.clearCart()
		cart.addItem({ ...item, item_code: "B", item_name: "B", rate: 20, price_list_rate: 20 })
		cart.addItem({ ...item })
		const b = cart.invoiceItems[0]
		b.free_qty = 1
		b.pricing_rules = ["RB"]
		cart.rebuildIncrementalCache()
		expect(cart.grandTotal).toBe(70)
		server.draft = {
			name: "SINV-CHECK",
			grand_total: 55,
			discount_amount: 0,
			items: [
				{ item_code: "B", is_free_item: 0, discount_amount: 0 },
				{ item_code: "B", is_free_item: 1, discount_amount: 0 },
				{
					item_code: "A",
					is_free_item: 0,
					qty: 1,
					rate: 35,
					discount_amount: 15,
					discount_percentage: 30,
					posnext_discount_source: "friends_and_family",
				},
			],
			friends_and_family: {
				eligible: true,
				discount_percentage: 30,
				applied_count: 1,
				items: [
					{ idx: 0, applies: false },
					{ idx: 1, applies: false },
					{ idx: 2, applies: true, discount_percentage: 30, discount_amount: 15, rate: 35 },
				],
			},
		}

		await check.requestPayment()

		const a = cart.invoiceItems.find((row) => row.item_code === "A")
		expect(a.discount_source).toBe("friends_and_family")
		expect(a.discount_amount).toBe(15)
		expect(cart.grandTotal).toBe(55)
	})

	it("a header changed after the check makes the submit re-check", async () => {
		server.draft = draft(0)
		await check.requestPayment()
		expect(openPayment).toHaveBeenCalledTimes(1)
		cart.additionalDiscount = 5
		cart.payments = [{ mode_of_payment: "Cash", amount: 45 }]

		await expect(cart.submitInvoice()).rejects.toThrow("changed after its total was checked")
		expect(server.submits).toHaveLength(0)
	})
})
