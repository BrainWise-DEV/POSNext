/**
 * An order discount and a whole-cart coupon never overwrite each other silently.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
	return { header: 0, rules: [], sent: [] }
})
const toast = vi.hoisted(() => ({}))
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({ valid: true })),
	createResource: () => {
		const submit = vi.fn(async ({ invoice_data, selected_offers }) => {
			server.sent.push(invoice_data)
			return {
				items: [],
				free_items: [],
				applied_pricing_rules: server.rules.filter((rule) =>
					selected_offers.includes(rule),
				),
				discount_amount: server.header,
			}
		})
		return { submit, reload: vi.fn(), fetch: vi.fn() }
	},
}))
vi.mock("@/composables/useToast", () => ({
	useToast: () => {
		Object.assign(toast, {
			showSuccess: vi.fn(),
			showError: vi.fn(),
			showWarning: vi.fn(),
			showInfo: vi.fn(),
		})
		return toast
	},
}))
vi.mock("@/utils/offline", () => ({
	isOffline: () => false,
	getCachedItem: vi.fn(),
}))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("../posCart")

const tv = {
	item_code: "TV",
	item_name: "TV",
	rate: 1000,
	price_list_rate: 1000,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
}
const coupon = { name: "C50", code: "C50", percentage: 0, amount: 50 }
const order = { name: "ORDER100" }

describe("order discount vs whole-cart coupon", () => {
	let cart
	beforeEach(() => {
		setActivePinia(createPinia())
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = "CUST-1"
		cart.addItem({ ...tv })
		Object.assign(server, { header: 100, rules: ["ORDER100"], sent: [] })
	})

	it("refuses a coupon while an order discount applies", async () => {
		await cart.applyOffer(order, {})
		expect(cart.additionalDiscount).toBe(100)
		expect(cart.applyDiscountToCart({ ...coupon })).toBe(false)
		expect(cart.appliedCoupon).toBeNull()
		expect(cart.additionalDiscount).toBe(100)
		expect(toast.showWarning).toHaveBeenCalledWith(
			expect.stringContaining("C50"),
		)
	})

	it("removes the coupon, and says so, when an order discount applies after it", async () => {
		cart.applyDiscountToCart({ ...coupon })
		expect(cart.additionalDiscount).toBe(50)
		await cart.applyOffer(order, {})
		expect(cart.appliedCoupon).toBeNull()
		expect(cart.additionalDiscount).toBe(100)
		expect(toast.showWarning).toHaveBeenCalledWith(
			expect.stringContaining("C50"),
		)
	})

	it("does not send the coupon's amount, so it is not echoed back as an order discount", async () => {
		cart.applyDiscountToCart({ ...coupon })
		server.header = 0
		server.rules = []
		await cart.applyOffer(order, {})
		expect(server.sent[0].discount_amount).toBe(0)
		expect(cart.appliedCoupon?.code).toBe("C50")
		expect(cart.additionalDiscount).toBe(50)
	})

	it("accepts the coupon once the order discount is removed", async () => {
		await cart.applyOffer(order, {})
		await cart.removeOffer("ORDER100", {})
		expect(cart.additionalDiscount).toBe(0)
		cart.applyDiscountToCart({ ...coupon })
		expect(cart.appliedCoupon?.code).toBe("C50")
		expect(cart.additionalDiscount).toBe(50)
	})

	it("keeps the order discount when the coupon is removed", async () => {
		cart.applyDiscountToCart({ ...coupon })
		cart.removeDiscountFromCart()
		await cart.applyOffer(order, {})
		expect(cart.additionalDiscount).toBe(100)
	})
})
