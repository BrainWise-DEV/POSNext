/**
 * D-R4-09 (b): a customer change that drops the applied coupon says so, even when the
 * F&F message for the new customer comes right after (one toast at a time: the F&F
 * toast used to replace the coupon one, so the cashier never learned the coupon went).
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const toast = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? s.replace(/\{(\d+)\}/g, (_, i) => args[i]) : s)
	window.posnext_app_flags = { posnext_promotions: 1 }
	return { showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }
})
const FNF_BLOCK = "No Friends & Family: verify the email first"
vi.mock("frappe-ui", () => ({
	call: vi.fn(async (method) =>
		String(method).includes("check_friends_and_family_eligibility")
			? { eligible: false, reason: "email_not_verified", message: FNF_BLOCK, customer: "CUST-NEW" }
			: {}
	),
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn() }),
}))
vi.mock("@/composables/useToast", () => ({ useToast: () => toast }))
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("../posCart")

const item = { item_code: "A", item_name: "A", rate: 100, price_list_rate: 100, uom: "Nos", stock_uom: "Nos", conversion_factor: 1 }
const lineCoupon = {
	name: "UIT-L20",
	code: "UIT-L20",
	line_level: true,
	coupon: { coupon_code: "UIT-L20", discount_type: "Percentage", discount_percentage: 20 },
	line_updates: [{ line_key: 0, item_code: "A", discount_percentage: 20, discount_amount: 0, rate: 80, amount: 80 }],
}

describe("D-R4-09 b: the dropped coupon is named with the F&F message", () => {
	let cart
	beforeEach(() => {
		setActivePinia(createPinia())
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = { name: "CUST-OLD" }
		cart.addItem({ ...item })
		cart.applyDiscountToCart(lineCoupon)
		toast.showWarning.mockClear()
	})

	it("the last toast names both the removed coupon and the F&F block", async () => {
		await cart.setCustomer({ name: "CUST-NEW" })
		const last = toast.showWarning.mock.calls.at(-1)?.[0] || ""
		expect(last).toContain("Coupon UIT-L20 removed: the customer changed")
		expect(last).toContain(FNF_BLOCK)
	})
})
