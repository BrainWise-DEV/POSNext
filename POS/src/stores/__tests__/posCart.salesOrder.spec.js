/**
 * Switching the cart to a Sales Order drops F&F; switching back re-runs offers.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const toast = vi.hoisted(() => {
	globalThis.__ = (s) => s
	return {}
})
const sent = vi.hoisted(() => [])
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: () => ({
		submit: vi.fn(async ({ data } = {}) => {
			if (data) sent.push(data)
			return { name: "DRAFT-1" }
		}),
		reload: vi.fn(), fetch: vi.fn() }),
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
const { useInvoice } = await import("@/composables/useInvoice")
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

describe("F&F on a Sales Order", () => {
	let cart
	beforeEach(() => {
		setActivePinia(createPinia())
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = "CUST-1"
		cart.addItem({ ...tv })
		stampFnfLine(cart.invoiceItems[0], { discount_percentage: 30, discount_amount: 300, rate: 700 })
		cart.invoiceItems[0].amount = 700
	})

	it("switching to sales order shows notice", () => {
		cart.setTargetDoctype("Sales Order")
		const line = cart.invoiceItems[0]
		expect(line.discount_amount).toBe(0)
		expect(line.discount_source).toBe("")
		expect(line.amount).toBe(1000)
		expect(toast.showInfo).toHaveBeenCalledWith(
			"Friends & Family discounts apply to invoices only",
		)
	})

	it("says nothing when no line carried F&F", () => {
		cart.invoiceItems[0].discount_source = ""
		cart.setTargetDoctype("Sales Order")
		expect(toast.showInfo).not.toHaveBeenCalled()
	})

	it("switching back reapplies offers", async () => {
		cart.setTargetDoctype("Sales Order")
		cart.offerProcessingState.lastCartHash = "stale"
		cart.setTargetDoctype("Sales Invoice")
		await vi.waitFor(() => expect(cart.offerProcessingState.lastCartHash).not.toBe("stale"))
	})
})

describe("Sales Order payload", () => {
	const line = {
		...tv,
		quantity: 1,
		qty: 1,
		amount: 700,
		discount_percentage: 30,
		discount_amount: 300,
		discount_source: "friends_and_family",
	}
	function invoice() {
		const inv = useInvoice()
		inv.posProfile.value = "POS-1"
		inv.customer.value = "CUST-1"
		inv.invoiceItems.value = [{ ...line }]
		return inv
	}
	beforeEach(() => {
		sent.length = 0
	})

	it("sales order draft carries no F&F discount", async () => {
		await invoice().saveDraft("Sales Order")
		expect(sent[0].items[0]).toMatchObject({ discount_amount: 0, discount_percentage: 0 })
		expect(sent[0].items[0].rate).toBe(1000)
	})

	it("invoice payload untouched", async () => {
		await invoice().saveDraft("Sales Invoice")
		expect(sent[0].items[0]).toMatchObject({ discount_amount: 300, discount_percentage: 30 })
	})
})
