import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const submit = vi.fn()

vi.mock("frappe-ui", () => ({
	createResource: () => ({
		submit,
		fetch: vi.fn(),
		reload: vi.fn(),
		data: null,
	}),
	call: vi.fn(),
}))
vi.mock("@/utils/offline", () => ({
	isOffline: () => true,
	getCachedItem: vi.fn(),
}))
vi.mock("@/stores/serialNumber", () => ({
	useSerialNumberStore: () => ({ returnSerials: vi.fn() }),
}))

const { shiftState } = await import("@/composables/useShift")
const { useInvoice } = await import("../useInvoice")

describe("useInvoice default customer", () => {
	beforeEach(() => {
		setActivePinia(createPinia())
		submit.mockReset()
	})

	it("falls back to the cached POS Profile customer when the request fails", async () => {
		submit.mockRejectedValue(new Error("offline"))
		shiftState.value = {
			...shiftState.value,
			pos_profile: { name: "P1", customer: "Walk-in" },
		}
		const invoice = useInvoice()
		invoice.posProfile.value = "P1"
		await invoice.setDefaultCustomer()
		expect(invoice.customer.value).toEqual({
			name: "Walk-in",
			customer_name: "Walk-in",
		})
	})

	it("leaves no customer when the profile has none", async () => {
		submit.mockRejectedValue(new Error("offline"))
		shiftState.value = { ...shiftState.value, pos_profile: { name: "P1" } }
		const invoice = useInvoice()
		invoice.posProfile.value = "P1"
		await invoice.setDefaultCustomer()
		expect(invoice.customer.value).toBeNull()
	})
})
