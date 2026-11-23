/**
 * POS Settings "Create Only Sales Order": every cart is a Sales Order, so F&F is
 * stripped as the Order switch strips it (UI test D-R3-12).
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { nextTick, reactive } from "vue"

const toast = vi.hoisted(() => {
	globalThis.__ = (s) => s
	return {}
})
const settings = vi.hoisted(() => ({ state: null }))
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: () => ({ submit: vi.fn(async () => ({ name: "DRAFT-1" })), reload: vi.fn(), fetch: vi.fn() }),
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
	usePOSSettingsStore: () => settings.state,
}))

const { usePOSCartStore } = await import("../posCart")
const { stampFnfLine } = await import("@/utils/friendsAndFamily")

const tv = {
	item_code: "TV",
	item_name: "TV",
	rate: 1000,
	price_list_rate: 1000,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
}

function cartWithFnfLine() {
	const cart = usePOSCartStore()
	cart.posProfile = "POS-1"
	cart.customer = "CUST-1"
	cart.addItem({ ...tv })
	stampFnfLine(cart.invoiceItems[0], { discount_percentage: 30, discount_amount: 300, rate: 700 })
	cart.invoiceItems[0].amount = 700
	return cart
}

describe("Create Only Sales Order", () => {
	beforeEach(() => {
		setActivePinia(createPinia())
		settings.state = reactive({ shouldEnforceStockValidation: () => false, createOnlySalesOrder: false })
	})

	it("a cart made while the setting is on is a Sales Order", () => {
		settings.state.createOnlySalesOrder = true
		const cart = usePOSCartStore()
		expect(cart.targetDoctype).toBe("Sales Order")
		cart.clearCart()
		expect(cart.targetDoctype).toBe("Sales Order")
	})

	it("turning it on makes the open cart a Sales Order and strips its F&F", async () => {
		const cart = cartWithFnfLine()
		expect(cart.targetDoctype).toBe("Sales Invoice")
		settings.state.createOnlySalesOrder = true
		await nextTick()
		expect(cart.targetDoctype).toBe("Sales Order")
		expect(cart.invoiceItems[0].discount_amount).toBe(0)
		expect(cart.invoiceItems[0].discount_source).toBe("")
		expect(toast.showInfo).toHaveBeenCalledWith("Friends & Family discounts apply to invoices only")
	})

	it("the cart cannot be switched back to an invoice", async () => {
		settings.state.createOnlySalesOrder = true
		const cart = cartWithFnfLine()
		cart.setTargetDoctype("Sales Invoice")
		expect(cart.targetDoctype).toBe("Sales Order")
	})

	it("with the setting off the cart is an invoice", () => {
		const cart = usePOSCartStore()
		expect(cart.targetDoctype).toBe("Sales Invoice")
		cart.clearCart()
		expect(cart.targetDoctype).toBe("Sales Invoice")
	})
})
