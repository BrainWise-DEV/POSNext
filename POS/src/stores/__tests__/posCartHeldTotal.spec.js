/**
 * Review R1-m1: a held cart is listed at what it charges when resumed. A hold keeps
 * the lines (and a line coupon) but not an order-level coupon or a manual header
 * discount, so a cart with one is listed at its line sum, as it resumes; a cart whose
 * total a hold keeps is listed at the total it showed.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { toRaw } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
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
const { heldCartTotal } = await import("@/utils/draftTotal")

const item = { item_code: "A", item_name: "A", rate: 154, price_list_rate: 154, uom: "Nos", stock_uom: "Nos", conversion_factor: 1 }

/** Hold the cart as POSSale does, then resume its lines into a fresh cart. */
function holdAndResume(cart) {
	const draft = { items: JSON.parse(JSON.stringify(toRaw(cart.invoiceItems))), grand_total: cart.resumableGrandTotal() }
	setActivePinia(createPinia())
	const resumed = usePOSCartStore()
	for (const line of draft.items) resumed.invoiceItems.push(line)
	resumed.rebuildIncrementalCache()
	return { listed: heldCartTotal(draft), charged: resumed.grandTotal }
}

describe("held cart total = what the resumed cart charges (R1-m1)", () => {
	let cart
	beforeEach(() => {
		setActivePinia(createPinia())
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = "CUST-1"
		cart.addItem({ ...item })
	})

	it("a 154 cart with a −40 order coupon is listed at 154, what it charges on resume", () => {
		cart.applyDiscountToCart({ name: "O40", code: "O40", percentage: 0, amount: 40, coupon: { discount_type: "Amount" } })
		expect(cart.grandTotal).toBe(114)
		const { listed, charged } = holdAndResume(cart)
		expect(charged).toBe(154)
		expect(listed).toBe(charged)
	})

	it("a cart without a header discount is listed at the total it showed", () => {
		const { listed, charged } = holdAndResume(cart)
		expect(listed).toBe(154)
		expect(charged).toBe(154)
	})
})
