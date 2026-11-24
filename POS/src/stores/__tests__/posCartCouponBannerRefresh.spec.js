/**
 * F6: the "coupon applied instead of Friends & Family" banner shows the server's latest comparison.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { describe, expect, it, vi } from "vitest"
import { nextTick } from "vue"

vi.hoisted(() => {
	globalThis.__ = (s, args) =>
		args ? s.replace(/\{(\d+)\}/g, (_, i) => args[i]) : s
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: () => ({
		submit: vi.fn(async () => ({})),
		reload: vi.fn(),
		fetch: vi.fn(),
	}),
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
const comparison = (coupon, fnf) => ({
	message: `Coupon L50 (${coupon}) applied instead of the Friends & Family discount (${fnf})`,
	message_en: `Coupon L50 (${coupon}) applied instead of the Friends & Family discount (${fnf})`,
	message_ar: `L50 (${coupon}) / (${fnf})`,
})
vi.mock("@/utils/apiWrapper", () => ({
	call: vi.fn(async (method) =>
		String(method).includes("validate_coupon")
			? {
					valid: true,
					best_discount: { outcome: "other" },
					...comparison("150.00", "90.00"),
					line_updates: [
						{
							line_key: 0,
							item_code: "A",
							discount_percentage: 50,
							discount_amount: 0,
							rate: 50,
							amount: 150,
							coupon_code: "L50",
						},
					],
				}
			: {},
	),
}))

const { usePOSCartStore } = await import("../posCart")
const { offlineState } = await import("@/utils/offline/offlineState")

describe("coupon that beat Friends & Family", () => {
	it("refreshes the banner text when a quantity change is re-checked", async () => {
		vi.spyOn(offlineState, "isOffline", "get").mockReturnValue(false)
		setActivePinia(createPinia())
		const cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = "CUST-FF"
		cart.addItem({
			item_code: "A",
			item_name: "A",
			rate: 100,
			price_list_rate: 100,
			uom: "Nos",
			stock_uom: "Nos",
			conversion_factor: 1,
		})
		cart.applyDiscountToCart({
			name: "L50",
			code: "L50",
			line_level: true,
			coupon: {
				coupon_code: "L50",
				discount_type: "Percentage",
				discount_percentage: 50,
			},
			line_updates: [
				{
					line_key: 0,
					item_code: "A",
					discount_percentage: 50,
					discount_amount: 0,
					rate: 50,
					amount: 50,
					coupon_code: "L50",
				},
			],
			suppress_friends_and_family: true,
			fnf_message: comparison("50.00", "30.00"),
		})
		expect(cart.fnfCouponOverride.message_en).toContain("(50.00)")
		await nextTick() // the coupon and the quantity change are two cashier actions

		cart.updateItemQuantity("A", 3)

		const { call } = await import("@/utils/apiWrapper")
		// Debounced, then waits for an offer pass in flight (COUPON_REVALIDATE_MAX_WAIT_MS)
		await vi.waitFor(
			() =>
				expect(
					call.mock.calls.some(([method]) =>
						String(method).includes("validate_coupon"),
					),
				).toBe(true),
			{ timeout: 7000 },
		)
		await vi.waitFor(
			() => expect(cart.fnfCouponOverride?.message_en).toContain("(150.00)"),
			{ timeout: 3000 },
		)
		expect(cart.fnfCouponOverride.message_en).toContain("(90.00)")
		expect(cart.fnfCouponOverride.message_ar).toContain("150.00")
		expect(cart.fnfCouponOverride.code).toBe("L50")
	})
})
