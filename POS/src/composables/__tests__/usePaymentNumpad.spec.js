/**
 * An Enter that lands right as the payment dialog opens (the F9 press, a scanner's Enter suffix)
 * must not complete the sale.
 * @vitest-environment jsdom
 */
import { mount } from "@vue/test-utils"
import { afterEach, describe, expect, it, vi } from "vitest"
import { defineComponent, nextTick, ref } from "vue"
import { usePaymentNumpad } from "../usePaymentNumpad"

function setup() {
	const isEnabled = ref(false)
	const onEnter = vi.fn()
	const wrapper = mount(
		defineComponent({
			setup() {
				usePaymentNumpad({ isEnabled, onEnter })
				return () => null
			},
		}),
		{ attachTo: document.body },
	)
	return { isEnabled, onEnter, wrapper }
}

const pressEnter = () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }))

describe("usePaymentNumpad Enter guard", () => {
	afterEach(() => vi.useRealTimers())

	it("ignores Enter right after the dialog opens, then accepts it", async () => {
		vi.useFakeTimers()
		const { isEnabled, onEnter, wrapper } = setup()

		isEnabled.value = true
		await nextTick()
		pressEnter()
		expect(onEnter).not.toHaveBeenCalled()

		vi.advanceTimersByTime(600)
		pressEnter()
		expect(onEnter).toHaveBeenCalledTimes(1)
		wrapper.unmount()
	})
})
