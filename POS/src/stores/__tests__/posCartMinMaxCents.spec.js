/**
 * G6: a Min/Max "buy one" line is priced as the saved invoice prices it, so the
 * screen, the amount collected and the invoice match, online and offline.
 *
 * The server spreads the free unit as a per-unit discount and saves a per-unit
 * rate at currency precision (250 / 6 → 41.67, × 6 = 250.02). The answers and the
 * invoice totals are from nexus.local (fixtures-minmax-buy-one.json).
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
	return { offers: null, draft: null, updates: [], taxes: [] }
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: ({ url } = {}) => {
		const submit = vi.fn(async (params) => {
			if (String(url).endsWith("invoices.apply_offers")) return server.offers
			if (String(url).endsWith("invoices.update_invoice")) {
				server.updates.push(JSON.parse(JSON.stringify(params.data)))
				return { ...server.draft }
			}
			if (String(url).endsWith("pos_profile.get_taxes")) return server.taxes
			return { items: [], free_items: [], applied_pricing_rules: [], discount_amount: 0 }
		})
		return { submit, reload: vi.fn(), fetch: vi.fn() }
	},
}))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const fixture = (await import("./fixtures-minmax-buy-one.json")).default
const { usePOSCartStore } = await import("@/stores/posCart")
const { usePaymentOpenCheck } = await import("@/composables/usePaymentOpenCheck")
const { buildOfflineInvoiceData } = await import("@/utils/offlineInvoicePayload")
const { restorePreCouponDiscount, stashPreCouponDiscount } = await import("@/utils/couponLines")

const ITEM = {
	item_code: "_PNXT_TEST_ITEM_A",
	item_name: "Item A",
	rate: 50,
	price_list_rate: 50,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
}
const ITEM_B = { ...ITEM, item_code: "_PNXT_TEST_ITEM_B", item_name: "Item B", rate: 80, price_list_rate: 80 }
const ITEMS = { [ITEM.item_code]: ITEM, [ITEM_B.item_code]: ITEM_B }

const round2 = (value) => Math.round(value * 100) / 100

// Every buy-one answer captured from the server: ITEM_A at 50 and ITEM_B at 80.
const BUY_ONE_CASES = [...fixture.cases, ...fixture.cases_80]

/** A cart of `qty` × the item with the server's buy-one answer applied, as the cashier sees it. */
async function buyOneCart(qty, itemCode = ITEM.item_code) {
	const { line } = BUY_ONE_CASES.find((c) => c.qty === qty && c.line.item_code === itemCode)
	const cart = usePOSCartStore()
	cart.posProfile = "POS-1"
	cart.customer = "CUST-1"
	await cart.loadTaxRules("POS-1")
	cart.addItem({ ...ITEMS[itemCode] })
	cart.updateItemQuantity(itemCode, qty)
	cart.cancelPendingOfferProcessing()
	server.offers = { items: [{ ...line }], free_items: [], applied_pricing_rules: [fixture.rule] }
	await cart.applyOffer({ name: fixture.rule, title: "Buy one" }, "POS-1")
	return cart
}

/** A cart of one line with a cashier's own discount (no pricing rules). */
function manualCart({ item_code, qty, discount_amount, discount_percentage }) {
	const cart = usePOSCartStore()
	cart.addItem({ ...ITEMS[item_code] })
	cart.updateItemQuantity(item_code, qty)
	cart.cancelPendingOfferProcessing()
	const line = cart.invoiceItems[0]
	Object.assign(line, { discount_amount: discount_amount || 0, discount_percentage: discount_percentage || 0 })
	cart.recalculateItem(line)
	cart.rebuildIncrementalCache()
	return cart
}

/** What the server saves for the rows the cart sends: Σ rate × qty at currency precision. */
function savedTotal(rows) {
	return round2(rows.reduce((sum, row) => sum + round2(row.rate * row.qty), 0))
}

describe("G6: a Min/Max buy-one line is priced as the invoice saves it", () => {
	beforeEach(() => {
		setActivePinia(createPinia())
		Object.assign(server, { offers: null, draft: null, updates: [], taxes: [] })
	})

	for (const { qty, line: answer, invoice } of BUY_ONE_CASES) {
		it(`${answer.price_list_rate} × ${qty}: the line, the grand total and the amount to collect are the invoice's ${invoice.grand_total}`, async () => {
			const cart = await buyOneCart(qty, answer.item_code)
			const line = cart.invoiceItems[0]
			expect(line.amount).toBe(invoice.amount)
			expect(cart.grandTotal).toBe(invoice.grand_total)
			expect(cart.paymentTotal).toBe(invoice.grand_total)

			// The rows sent are the rows the server saves: same unit rate, same total.
			const [row] = cart.formatItemsForSubmission(cart.invoiceItems)
			expect(row.rate).toBe(invoice.rate)
			expect(savedTotal([row])).toBe(invoice.grand_total)

			// Online, the payment-open check finds the server's draft total equal to the cart's.
			server.draft = { name: "SINV-CHECK", grand_total: invoice.grand_total, discount_amount: 0 }
			const openPayment = vi.fn()
			const check = usePaymentOpenCheck({
				isOffline: () => false,
				checkPrice: () => cart.checkPriceBeforePayment(),
				openPayment,
				showError: vi.fn(),
			})
			expect(await check.requestPayment()).toBe(true)
			expect(cart.paymentTotal).toBe(cart.grandTotal)
		})
	}

	it("with a 15% tax, 6 × 50 collects the invoice's net, tax and grand total", async () => {
		server.taxes = [{ charge_type: "On Net Total", rate: fixture.taxed.tax_rate, account_head: "VAT" }]
		const cart = await buyOneCart(fixture.taxed.qty)
		const { invoice } = fixture.taxed
		expect(cart.invoiceItems[0].amount).toBe(invoice.net_total)
		expect(cart.totalTax).toBe(invoice.tax)
		expect(cart.grandTotal).toBe(invoice.grand_total)
		expect(cart.paymentTotal).toBe(invoice.grand_total)
		const [row] = cart.formatItemsForSubmission(cart.invoiceItems)
		expect(row.rate).toBe(invoice.rate)
	})

	it("tax-inclusive, 6 × 50 sends the gross unit rate that reproduces the line", async () => {
		server.taxes = [{ charge_type: "On Net Total", rate: fixture.taxed.tax_rate, account_head: "VAT" }]
		const cart = await buyOneCart(fixture.taxed.qty)
		cart.setTaxInclusive(true)
		const [row] = cart.formatItemsForSubmission(cart.invoiceItems)
		expect(row.rate).toBe(41.67)
		expect(cart.grandTotal).toBe(savedTotal([row]))
		expect(cart.grandTotal).toBe(250.02)
	})

	it("a server draft that reprices the line at a 2-dp % is adopted at its rate (m-3)", async () => {
		const cart = await buyOneCart(6)
		// The cart's line went stale (another %); the server's draft row has 16.67% and 41.67.
		const line = cart.invoiceItems[0]
		line.discount_percentage = 10
		cart.recalculateItem(line)
		cart.rebuildIncrementalCache()
		server.draft = {
			name: "SINV-CHECK",
			grand_total: 250.02,
			discount_amount: 0,
			items: [{ item_code: ITEM.item_code, qty: 6, price_list_rate: 50, rate: 41.67, discount_percentage: 16.67, discount_amount: 8.33, pricing_rules: fixture.rule }],
		}
		const check = usePaymentOpenCheck({
			isOffline: () => false,
			checkPrice: () => cart.checkPriceBeforePayment(),
			openPayment: vi.fn(),
			showError: vi.fn(),
		})
		await check.requestPayment()
		expect(cart.invoiceItems[0].amount).toBe(250.02)
		expect(cart.grandTotal).toBe(250.02)
		expect(cart.paymentTotal).toBe(cart.grandTotal)
		expect(savedTotal(cart.formatItemsForSubmission(cart.invoiceItems))).toBe(250.02)
	})

	for (const qty of [3, 6, 7]) {
		it(`offline, qty ${qty}: the queued sale is paid what the server will save`, async () => {
			const cart = await buyOneCart(qty)
			const { invoice } = fixture.cases.find((c) => c.qty === qty)
			// No payment-open check offline: the payment dialog collects the cart's own total.
			cart.payments = [{ mode_of_payment: "Cash", amount: cart.paymentTotal }]
			const data = buildOfflineInvoiceData({
				cart,
				shift: { profileCompany: "C", profileCustomer: "Walk-in" },
				customer: "CUST-1",
				paymentData: {},
			})
			const paid = round2(data.payments.reduce((sum, p) => sum + p.amount, 0))
			expect(paid).toBe(data.grand_total)
			expect(paid).toBe(savedTotal(data.items))
			expect(paid).toBe(invoice.grand_total)
		})
	}
})

describe("G8: a cashier's own discount is priced as the invoice saves it", () => {
	beforeEach(() => {
		setActivePinia(createPinia())
		Object.assign(server, { offers: null, draft: null, updates: [], taxes: [] })
	})

	for (const manual of fixture.manual) {
		const what = manual.discount_amount ? `${manual.discount_amount} off` : `${manual.discount_percentage}% of`
		it(`${what} ${manual.qty} × ${manual.price}: the cart shows, collects and sends the invoice's ${manual.invoice.grand_total}`, () => {
			const cart = manualCart(manual)
			expect(cart.grandTotal).toBe(manual.invoice.grand_total)
			expect(cart.paymentTotal).toBe(manual.invoice.grand_total)
			const [row] = cart.formatItemsForSubmission(cart.invoiceItems)
			expect(row.rate).toBe(manual.invoice.rate)
			expect(savedTotal([row])).toBe(manual.invoice.grand_total)
		})
	}

	it("a manually edited rate with a % sends the unit rate that reproduces the line", () => {
		const cart = usePOSCartStore()
		cart.addItem({ ...ITEM })
		cart.updateItemQuantity(ITEM.item_code, 3)
		cart.cancelPendingOfferProcessing()
		const line = cart.invoiceItems[0]
		// 33.33 typed as the rate, 7% off: 31.00 a unit (line basis gave 92.99, saved 93.00).
		Object.assign(line, { is_rate_manually_edited: 1, rate: 33.33, discount_percentage: 7 })
		cart.recalculateItem(line)
		cart.rebuildIncrementalCache()
		const [row] = cart.formatItemsForSubmission(cart.invoiceItems)
		expect(row.rate).toBe(31)
		expect(cart.grandTotal).toBe(93)
		expect(savedTotal([row])).toBe(cart.grandTotal)
	})

	it("an amount discount is never eroded by qty changes: 10 off stays 10 when it splits again", () => {
		const cart = manualCart(fixture.manual[0]) // 10 off 3 × 50 → 3.33 a unit, 9.99
		cart.updateItemQuantity(ITEM.item_code, 4) // 2.50 a unit, 10.00
		expect(cart.invoiceItems[0].discount_amount).toBe(10)
		expect(cart.invoiceItems[0].amount).toBe(190)
		cart.updateItemQuantity(ITEM.item_code, 3)
		expect(cart.invoiceItems[0].discount_amount).toBe(9.99)
		expect(cart.invoiceItems[0].amount).toBe(140.01)
	})

	// pos-dev probe (G8 round 1): a 15% inclusive template on a POS Profile with
	// tax_inclusive set saves grand = gross, and the net and tax the cart computes.
	for (const [what, fields, grand, tax] of [
		["10 off 3 × 50", { item_code: ITEM.item_code, qty: 3, discount_amount: 10 }, 140.01, 18.26],
		["16.67% of 6 × 50", { item_code: ITEM.item_code, qty: 6, discount_percentage: 16.67 }, 249.96, 32.6],
		["30 off 7 × 50", { item_code: ITEM.item_code, qty: 7, discount_amount: 30 }, 320.04, 41.74],
	]) {
		it(`tax-inclusive 15%, ${what}: the cart's gross, tax and sent rate are the invoice's`, async () => {
			server.taxes = [{ charge_type: "On Net Total", rate: 15, account_head: "VAT" }]
			const cart = manualCart(fields)
			await cart.loadTaxRules("POS-1")
			cart.setTaxInclusive(true)
			expect(cart.grandTotal).toBe(grand)
			expect(cart.totalTax).toBe(tax)
			expect(savedTotal(cart.formatItemsForSubmission(cart.invoiceItems))).toBe(grand)
		})
	}

	it("typing exactly the applied figure makes it the new request (m-2a)", async () => {
		const cart = manualCart(fixture.manual[0]) // 10 off 3 × 50 → 9.99
		await cart.updateItemDetails(ITEM.item_code, { discount_amount: 9.99, discount_percentage: 0 })
		cart.updateItemQuantity(ITEM.item_code, 4) // 9.99 over 4: 2.49 a unit
		expect(cart.invoiceItems[0].discount_amount).toBe(9.96)
	})

	it("removing a coupon gives back the amount asked for, not its rounding (m-2b)", () => {
		const cart = manualCart(fixture.manual[0]) // 10 off 3 × 50 → 9.99
		const line = cart.invoiceItems[0]
		stashPreCouponDiscount(line)
		Object.assign(line, { discount_amount: 20, discount_percentage: 0, discount_source: "coupon", coupon_code: "SAVE20" })
		cart.recalculateItem(line)
		restorePreCouponDiscount(line)
		line.quantity = 4
		cart.recalculateItem(line)
		expect(line.discount_amount).toBe(10)
	})

	it("offline, a manual amount discount is queued paid at what the server will save", () => {
		const cart = manualCart(fixture.manual[1]) // 30 off 7 × 50
		cart.payments = [{ mode_of_payment: "Cash", amount: cart.paymentTotal }]
		const data = buildOfflineInvoiceData({
			cart,
			shift: { profileCompany: "C", profileCustomer: "Walk-in" },
			customer: "CUST-1",
			paymentData: {},
		})
		const paid = round2(data.payments.reduce((sum, p) => sum + p.amount, 0))
		expect(paid).toBe(data.grand_total)
		expect(paid).toBe(savedTotal(data.items))
	})
})
