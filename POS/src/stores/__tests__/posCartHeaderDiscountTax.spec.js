/**
 * D-R2-07: with a header discount on the Grand Total, the cart shows the tax the
 * server saves. ERPNext spreads the discount over the total with tax, so the tax
 * falls with it (UIT-O100: 280 + 42 − 100 → net 193.04, tax 28.96, total 222).
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: () => ({
		submit: vi.fn(async () => [{ charge_type: "On Net Total", rate: 15 }]),
		reload: vi.fn(),
		fetch: vi.fn(),
	}),
}))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock("@/utils/offline", () => ({
	isOffline: () => false,
	getCachedItem: vi.fn(),
}))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("../posCart")
const { taxAfterHeaderDiscount } = await import("@/utils/currency")

const item = (code, rate) => ({
	item_code: code,
	item_name: code,
	rate,
	price_list_rate: rate,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
})

describe("D-R2-07: tax after a Grand Total header discount", () => {
	let cart
	beforeEach(async () => {
		setActivePinia(createPinia())
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		await cart.loadTaxRules("POS-1")
		cart.addItem(item("A", 100), 2)
		cart.addItem(item("EXCL", 80))
	})

	it("UIT-O100: the order coupon's 100 takes the tax from 42 to 28.96; the total stays 222", () => {
		expect(cart.totalTax).toBeCloseTo(42, 2)
		cart.applyDiscountToCart({ name: "O100", code: "O100", amount: 100, percentage: 0 })
		expect(cart.additionalDiscount).toBe(100)
		expect(cart.totalTax).toBeCloseTo(28.96, 2)
		expect(cart.grandTotal).toBeCloseTo(222, 2)
	})

	it("no header discount: the tax is unchanged", () => {
		expect(cart.totalTax).toBeCloseTo(42, 2)
		expect(cart.grandTotal).toBeCloseTo(322, 2)
	})

	it("the tax falls with the share of the total the discount takes", () => {
		// 42 × (1 − 100 / 322): the total before the discount holds the tax, on top or inclusive
		expect(taxAfterHeaderDiscount({ tax: 42, total: 322, discount: 100 })).toBeCloseTo(28.96, 2)
		// A discount of the whole total leaves no tax
		expect(taxAfterHeaderDiscount({ tax: 42, total: 322, discount: 322 })).toBe(0)
		expect(taxAfterHeaderDiscount({ tax: 0, total: 280, discount: 100 })).toBe(0)
		expect(taxAfterHeaderDiscount({ tax: 42, total: 322, discount: 0 })).toBe(42)
	})

	it("a Net Total discount keeps the cart's tax (not handled here)", () => {
		expect(taxAfterHeaderDiscount({ tax: 42, total: 322, discount: 100, applyDiscountOn: "Net Total" })).toBe(42)
	})
})

describe("Round 1 (Ruling 150): a display fix never changes a total or a money input", () => {
	let cart
	beforeEach(async () => {
		setActivePinia(createPinia())
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		await cart.loadTaxRules("POS-1")
		cart.addItem(item("A", 100), 2)
		cart.addItem(item("EXCL", 80))
		cart.applyDiscountToCart({ name: "O100", code: "O100", amount: 100, percentage: 0 })
	})

	it("C1: the cart footer's Grand Total for UIT-O100 is the 222 collected, with the Tax row at 28.96", async () => {
		const { cartDisplayTotals } = await import("@/utils/cartLineLabels")
		expect(cart.lineTotalTax).toBeCloseTo(42, 2)
		const totals = cartDisplayTotals({
			subtotal: cart.subtotal,
			lineTax: cart.lineTotalTax,
			discount: cart.totalDiscount,
			taxInclusive: false,
		})
		expect(totals.grandTotal).toBeCloseTo(222, 2)
		expect(totals.grandTotal).toBeCloseTo(cart.grandTotal, 2)
		expect(cart.totalTax).toBeCloseTo(28.96, 2)
		// Tax-inclusive: the same 222 and a subtotal net of the lines' tax
		const inclusive = cartDisplayTotals({ subtotal: 322, lineTax: 42, discount: 100, taxInclusive: true })
		expect(inclusive).toEqual({ subtotal: 280, grandTotal: 222 })
	})

	it("C1/I1: the cart footer and the coupon dialog get the pre-discount tax", async () => {
		const fs = await import("node:fs")
		const path = await import("node:path")
		const src = (rel) => fs.readFileSync(path.resolve(__dirname, "..", "..", rel), "utf8")
		// I1: the coupon's net base (grand − tax) must not move with the Tax row
		const couponDialog = src("pages/POSSale.vue").match(/<CouponDialog[\s\S]*?\/>/)[0]
		expect(couponDialog).toContain(':tax-amount="cartStore.lineTotalTax"')
		// C1: the footer totals come from cartDisplayTotals with the lines' tax
		const cartSfc = src("components/sale/InvoiceCart.vue")
		expect(cartSfc).toContain("lineTax: cartStore.lineTotalTax")
		expect(cartSfc).not.toMatch(/displaySubtotal\.value \+ props\.taxAmount/)
	})
})
