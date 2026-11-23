/**
 * D-R4-08: the Edit Item Details dialog is exposed as a dialog, named by its title,
 * like the Coupon and Payment dialogs (a screen reader or a test can find it by role).
 * @vitest-environment jsdom
 */
import { mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { describe, expect, it, vi } from "vitest"

vi.hoisted(() => {
	globalThis.__ = (s) => s
})
vi.mock("frappe-ui", () => ({
	Button: { template: "<button><slot /></button>" },
	FeatherIcon: { template: "<i />" },
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn(), data: null }),
	call: vi.fn(),
}))
vi.mock("@/utils/apiWrapper", () => ({ call: vi.fn(async () => []) }))
vi.mock("@/utils/salesPersonsList", () => ({ loadSalesPersonsForProfile: vi.fn(async () => []) }))

const { default: EditItemDialog } = await import("../EditItemDialog.vue")

describe("Edit Item Details dialog accessibility (D-R4-08)", () => {
	it("is a modal dialog named by its title, with a named close button", async () => {
		setActivePinia(createPinia())
		const wrapper = mount(EditItemDialog, {
			props: {
				modelValue: true,
				item: { item_code: "A", item_name: "A", quantity: 1, rate: 50, price_list_rate: 50, uom: "Nos" },
			},
			global: {
				stubs: { Teleport: true, Transition: false, SelectInput: true },
				mocks: { __: (s) => s },
			},
			attachTo: document.body,
		})
		const dialog = document.querySelector("[role=dialog]")
		expect(dialog).not.toBeNull()
		expect(dialog.getAttribute("aria-modal")).toBe("true")
		const title = document.getElementById(dialog.getAttribute("aria-labelledby"))
		expect(title?.textContent.trim()).toBe("Edit Item Details")
		expect(dialog.querySelector("button[aria-label='Close']")).not.toBeNull()
		wrapper.unmount()
	})
})
