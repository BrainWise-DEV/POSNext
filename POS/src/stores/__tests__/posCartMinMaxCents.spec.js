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
	return { offers: null, draft: null, updates: [] }
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
			if (String(url).endsWith("pos_profile.get_taxes")) return []
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

const ITEM = {
	item_code: "_PNXT_TEST_ITEM_A",
	item_name: "Item A",
	rate: 50,
	price_list_rate: 50,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
}

const round2 = (value) => Math.round(value * 100) / 100

/** A cart of `qty` × ITEM_A with the server's buy-one answer applied, as the cashier sees it. */
async function buyOneCart(qty) {
	const { line } = fixture.cases.find((c) => c.qty === qty)
	const cart = usePOSCartStore()
	cart.posProfile = "POS-1"
	cart.customer = "CUST-1"
	cart.addItem({ ...ITEM })
	cart.updateItemQuantity(ITEM.item_code, qty)
	cart.cancelPendingOfferProcessing()
	server.offers = { items: [{ ...line }], free_items: [], applied_pricing_rules: [fixture.rule] }
	await cart.applyOffer({ name: fixture.rule, title: "Buy one" }, "POS-1")
	return cart
}

/** What the server saves for the rows the cart sends: Σ rate × qty at currency precision. */
function savedTotal(rows) {
	return round2(rows.reduce((sum, row) => sum + round2(row.rate * row.qty), 0))
}

describe("G6: a Min/Max buy-one line is priced as the invoice saves it", () => {
	beforeEach(() => {
		setActivePinia(createPinia())
		Object.assign(server, { offers: null, draft: null, updates: [] })
	})

	for (const { qty, invoice } of fixture.cases) {
		it(`qty ${qty}: the line, the grand total and the amount to collect are the invoice's ${invoice.grand_total}`, async () => {
			const cart = await buyOneCart(qty)
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

	it("a cashier's own % on a line without pricing rules keeps the line basis", () => {
		const cart = usePOSCartStore()
		cart.addItem({ ...ITEM })
		cart.updateItemQuantity(ITEM.item_code, 6)
		cart.cancelPendingOfferProcessing()
		const line = cart.invoiceItems[0]
		Object.assign(line, { discount_percentage: 100 / 6, pricing_rules: [] })
		cart.recalculateItem(line)
		expect(line.amount).toBe(250)
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
