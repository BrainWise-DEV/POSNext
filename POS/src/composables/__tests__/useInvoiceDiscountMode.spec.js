import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("frappe-ui", () => ({
	createResource: () => ({ submit: vi.fn(), fetch: vi.fn(), reload: vi.fn(), data: null }),
	call: vi.fn(),
}))
vi.mock("@/utils/offline", () => ({
	isOffline: () => true,
	getCachedItem: vi.fn(),
}))
vi.mock("@/stores/serialNumber", () => ({
	useSerialNumberStore: () => ({ returnSerials: vi.fn() }),
}))

const { useInvoice } = await import("../useInvoice")

function setup() {
	const inv = useInvoice()
	inv.addItem(
		{ item_code: "A", rate: 250, price_list_rate: 250, uom: "Nos", stock_uom: "Nos", conversion_factor: 1 },
		2,
	)
	return { inv, item: inv.invoiceItems.value[0] }
}

describe("useInvoice line discount mode", () => {
	beforeEach(() => setActivePinia(createPinia()))

	it("keeps a fixed-amount discount fixed across qty changes (no flicker)", () => {
		const { inv, item } = setup()
		item.discount_amount = 20
		inv.recalculateItem(item)
		expect(item.amount).toBe(480)

		inv.updateItemQuantity("A", 3)
		const after3 = inv.invoiceItems.value[0]
		expect(after3.discount_amount).toBe(20)
		expect(after3.amount).toBe(730)

		inv.updateItemQuantity("A", 2)
		const back = inv.invoiceItems.value[0]
		expect(back.discount_amount).toBe(20)
		expect(back.amount).toBe(480)
	})

	it("still scales a real percentage discount with qty", () => {
		const { inv, item } = setup()
		item.discount_percentage = 10
		inv.recalculateItem(item)
		expect(item.amount).toBe(450)
		inv.updateItemQuantity("A", 3)
		expect(inv.invoiceItems.value[0].amount).toBe(675)
	})

	it("switches back to percentage when a new percentage is written", () => {
		const { inv, item } = setup()
		item.discount_amount = 20
		inv.recalculateItem(item)
		item.discount_percentage = 10
		item.discount_amount = 0
		inv.recalculateItem(item)
		expect(item.discount_amount).toBe(50)
		expect(item.amount).toBe(450)
	})
})
