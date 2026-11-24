/**
 * F2: typing a quantity removes the line only when the cashier confirms a zero or negative value.
 * @vitest-environment jsdom
 */
import { mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { describe, expect, it, vi } from "vitest"

vi.hoisted(() => {
	globalThis.__ = (s, args) =>
		args ? s.replace(/\{(\d+)\}/g, (_, i) => args[i]) : s
})
vi.mock("frappe-ui", () => ({
	FeatherIcon: { template: "<i />" },
	createResource: () => ({
		submit: vi.fn(),
		reload: vi.fn(),
		fetch: vi.fn(),
		data: null,
	}),
	call: vi.fn(async () => ({})),
}))
vi.mock("@/utils/apiWrapper", () => ({ call: vi.fn(async () => ({})) }))
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
vi.mock("@/utils/offline/workerClient", () => ({
	offlineWorker: new Proxy({}, { get: () => async () => null }),
}))

const { default: InvoiceCart } = await import("../InvoiceCart.vue")

const line = {
	item_code: "UIT-A",
	item_name: "UIT-A",
	uom: "Kg",
	stock_uom: "Kg",
	quantity: 1,
	rate: 100,
	price_list_rate: 100,
	amount: 100,
}

function mountCart() {
	setActivePinia(createPinia())
	const wrapper = mount(InvoiceCart, {
		props: {
			items: [line],
			subtotal: 100,
			grandTotal: 100,
			posProfile: "UIT-FF Profile",
			currency: "EGP",
		},
		global: {
			mocks: { __: globalThis.__ },
			stubs: { EditItemDialog: true, Teleport: true },
		},
	})
	return {
		wrapper,
		box: wrapper.get('[data-line-key] input[aria-label="Quantity"]'),
	}
}

describe("typing a quantity", () => {
	it("keeps the line while the cashier types the leading 0 of 0.5", async () => {
		const { wrapper, box } = mountCart()
		await box.setValue("0")
		expect(wrapper.emitted("remove-item")).toBeUndefined()
	})

	it("sets 0.5 once the cashier has typed it", async () => {
		const { wrapper, box } = mountCart()
		await box.setValue("0")
		await box.setValue("0.5")
		expect(wrapper.emitted("update-quantity").at(-1)).toEqual([
			"UIT-A",
			0.5,
			"Kg",
		])
	})

	it("removes the line when 0 is confirmed by leaving the box", async () => {
		const { wrapper, box } = mountCart()
		await box.setValue("0")
		await box.trigger("blur")
		expect(wrapper.emitted("remove-item")).toEqual([["UIT-A", "Kg"]])
	})

	it("removes the line when a negative quantity is confirmed with Enter", async () => {
		const { wrapper, box } = mountCart()
		await box.setValue("-3")
		await box.trigger("keydown", { key: "Enter" })
		await box.trigger("blur")
		expect(wrapper.emitted("remove-item")).toEqual([["UIT-A", "Kg"]])
	})
})
