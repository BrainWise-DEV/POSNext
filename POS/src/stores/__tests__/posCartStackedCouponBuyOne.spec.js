/**
 * D-R4-03 (cart side): a 10% "Add on top" coupon on a Min/Max "buy one" line (6 × 50,
 * 250.02 at 41.67 a unit). The server stacks the coupon on the promoted unit rate
 * (41.67 × 0.9 = 37.503) and saves 37.50 a unit, 225.00. The cart priced the line
 * at 37.51 (225.06, the coupon's line discount floored to whole cents a unit) and the
 * header chip summed the server's unrounded shares (28.00) while the lines gave 27.96.
 * The line now takes the server's unit rate at currency precision, and the chip is what
 * the lines take.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({ valid: true })),
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn() }),
}))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("../posCart")

const item = (code) => ({
	item_code: code,
	item_name: code,
	rate: 50,
	price_list_rate: 50,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
})
const coupon = { coupon_code: "UIT-L10", discount_type: "Percentage", discount_percentage: 10 }

// What validate_coupon answers for the cart (coupon_engine.apply_coupon_to_items, "line" basis).
const updates = [
	{
		// UIT-C: 40% off (30 a unit), 10% of 30 on top -> 27.
		line_key: 0,
		item_code: "UIT-C",
		discount_percentage: 0,
		discount_amount: 23,
		rate: 27,
		amount: 27,
		coupon_code: "UIT-L10",
		coupon_only_discount: 3,
		existing_discount: 20,
		stacked: true,
	},
	{
		// Buy one on 6 × 50: 250.02 (49.98 off); 10% of 250.02 on top.
		line_key: 1,
		item_code: "BUY50",
		discount_percentage: 0,
		discount_amount: 74.982,
		rate: 37.503,
		amount: 225.018,
		coupon_code: "UIT-L10",
		coupon_only_discount: 25.002,
		existing_discount: 49.98,
		stacked: true,
	},
]

describe("Add on top coupon on a buy-one line (D-R4-03 cart)", () => {
	let cart
	beforeEach(() => {
		setActivePinia(createPinia())
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = "CUST-1"
		cart.addItem(item("UIT-C"))
		cart.addItem(item("BUY50"), 6)
		const [c, buy] = cart.invoiceItems
		c.discount_percentage = 40
		c.discount_source = "promotion"
		buy.quantity = 6
		buy.discount_amount = 49.98
		buy.discount_source = "promotion"
		cart.recalculateItem(c)
		cart.recalculateItem(buy)
		cart.applyDiscountToCart({ name: "UIT-L10", code: "UIT-L10", line_level: true, coupon, line_updates: updates })
	})

	it("prices the buy-one line at the server's 2-dp unit rate: 37.50 a unit, 225.00", () => {
		const buy = cart.invoiceItems[1]
		expect(buy.amount).toBe(225)
		const [, row] = cart.formatItemsForSubmission(cart.invoiceItems)
		expect(row.rate).toBe(37.5)
		expect(row.posnext_coupon_discount).toBe(25.02)
	})

	it("keeps the other stacked line as it was: 27.00", () => {
		expect(cart.invoiceItems[0].amount).toBe(27)
	})

	it("the header chip is what the lines take: 3.00 + 25.02", () => {
		expect(cart.appliedCoupon.amount).toBe(28.02)
	})
})
