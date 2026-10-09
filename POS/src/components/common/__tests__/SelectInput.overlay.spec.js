/**
 * SelectInput option lists must render on document.body above POS overlays.
 * @vitest-environment jsdom
 */
import { mount } from "@vue/test-utils"
import { describe, expect, it, vi } from "vitest"
import SelectInput from "../SelectInput.vue"

vi.mock("frappe-ui", () => ({
	FeatherIcon: {
		name: "FeatherIcon",
		props: ["name"],
		template: "<span />",
	},
}))

describe("SelectInput", () => {
	it("teleports the option list to body with dropdown stacking class", async () => {
		const wrapper = mount(SelectInput, {
			props: {
				modelValue: "all",
				options: [
					{ label: "All Status", value: "all" },
					{ label: "Active Only", value: "active" },
				],
			},
			attachTo: document.body,
		})

		await wrapper.find("button").trigger("click")

		const listbox = document.body.querySelector('[role="listbox"]')
		expect(listbox).toBeTruthy()
		expect(listbox.className).toContain("dropdown-z-index")
		expect(listbox.textContent).toContain("Active Only")

		wrapper.unmount()
	})

	it("widens the option list when minDropdownWidth exceeds the trigger", async () => {
		const wrapper = mount(SelectInput, {
			props: {
				modelValue: "all",
				minDropdownWidth: 180,
				options: [
					{ label: "All Status", value: "all" },
					{ label: "Active Only", value: "active" },
				],
			},
			attachTo: document.body,
		})

		await wrapper.find("button").trigger("click")

		const listbox = document.body.querySelector('[role="listbox"]')
		expect(listbox.style.width).toBe("180px")

		wrapper.unmount()
	})
})
