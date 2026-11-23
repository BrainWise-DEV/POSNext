/**
 * J1 (user request): every free gift renders as the same full-width card, whatever its
 * kind. A gift earned by a cart line (same-item BXGY, GWP, free item) names that line in a
 * caption instead of being indented under it.
 * @vitest-environment jsdom
 */
import { mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { describe, expect, it, vi } from "vitest"

vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? s.replace(/\{(\d+)\}/g, (_, i) => args[i]) : s)
})
vi.mock("frappe-ui", () => ({
	FeatherIcon: { template: "<i />" },
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn(), data: null }),
	call: vi.fn(async () => ({})),
}))
vi.mock("@/utils/apiWrapper", () => ({ call: vi.fn(async () => ({})) }))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }))
// Every worker call answers nothing (the cart only needs to render).
vi.mock("@/utils/offline/workerClient", () => ({
	offlineWorker: new Proxy({}, { get: () => async () => null }),
}))

const { default: InvoiceCart } = await import("../InvoiceCart.vue")

const paid = { item_code: "UIT-BXGY", item_name: "UIT-BXGY", uom: "Nos", stock_uom: "Nos", quantity: 5, rate: 60, price_list_rate: 60, amount: 300, pricing_rules: "UIT-PR-BXGY" }
const sameItemGift = { item_code: "UIT-BXGY", item_name: "UIT-BXGY", uom: "Nos", stock_uom: "Nos", quantity: 1, rate: 0, amount: 0, is_free_item: 1, pricing_rules: "UIT-PR-BXGY" }
const cartGift = { item_code: "UIT-GIFT", item_name: "UIT-GIFT", uom: "Nos", stock_uom: "Nos", quantity: 1, rate: 0, amount: 0, is_free_item: 1, pricing_rules: "UIT-PR-CART-GIFT" }

function mountCart(items) {
	setActivePinia(createPinia())
	return mount(InvoiceCart, {
		props: { items, subtotal: 300, grandTotal: 300, posProfile: "UIT-FF Profile", currency: "EGP" },
		global: {
			mocks: { __: globalThis.__ },
			stubs: { EditItemDialog: true, Teleport: true },
		},
	})
}

describe("free gift card", () => {
	it("the cart renders every kind of gift as the same full-width card; the earned one names its line", () => {
		const wrapper = mountCart([paid, sameItemGift, cartGift])
		const cards = wrapper.findAll('[data-testid="free-gift-row"]')
		expect(cards).toHaveLength(2)
		const [earned, cartTotal] = cards
		expect(earned.text()).toContain("UIT-BXGY")
		expect(cartTotal.text()).toContain("UIT-GIFT")
		// Same card, same classes: no indent for the gift a line earned.
		expect(earned.classes()).toEqual(cartTotal.classes())
		expect(earned.classes()).toContain("w-full")
		expect(earned.classes().some((c) => /^-?(ms|ml|ps|pl|mt)-/.test(c))).toBe(false)
		// The link to the line that earned it is kept, as a caption and an attribute.
		expect(earned.attributes("data-gift-of")).toBe("UIT-BXGY-Nos")
		expect(earned.get('[data-testid="free-gift-for"]').text()).toBe("For UIT-BXGY")
		expect(cartTotal.find('[data-testid="free-gift-for"]').exists()).toBe(false)
		for (const card of cards) {
			expect(card.text()).toContain("Free gift")
			expect(card.text()).toContain("Free of charge")
		}
		// The earned gift follows its line.
		const order = wrapper.findAll('[data-line-key], [data-testid="free-gift-row"]').map((el) => el.attributes("data-line-key") || el.text().slice(0, 30))
		expect(order[0]).toBe("UIT-BXGY-Nos")
		expect(order[1]).toContain("UIT-BXGY")
	})
})
