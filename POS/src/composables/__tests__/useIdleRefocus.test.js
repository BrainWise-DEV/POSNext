import { ref } from "vue"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useIdleRefocus } from "@/composables/useIdleRefocus"

describe("useIdleRefocus", () => {
	beforeEach(() => {
		vi.useFakeTimers()
		document.body.innerHTML = ""
		if (document.activeElement?.blur) document.activeElement.blur()
	})
	afterEach(() => {
		vi.clearAllTimers()
		vi.useRealTimers()
	})

	it("refocuses after the configured idle interval when enabled", () => {
		const onRefocus = vi.fn()
		useIdleRefocus({
			enabled: ref(true),
			intervalSeconds: ref(2),
			isDialogOpen: ref(false),
			onRefocus,
		})
		vi.advanceTimersByTime(1999)
		expect(onRefocus).not.toHaveBeenCalled()
		vi.advanceTimersByTime(1)
		expect(onRefocus).toHaveBeenCalledTimes(1)
	})

	it("does not refocus while disabled", () => {
		const onRefocus = vi.fn()
		useIdleRefocus({
			enabled: ref(false),
			intervalSeconds: ref(1),
			isDialogOpen: ref(false),
			onRefocus,
		})
		vi.advanceTimersByTime(5000)
		expect(onRefocus).not.toHaveBeenCalled()
	})

	it("holds off (reschedules) while a dialog is open", () => {
		const onRefocus = vi.fn()
		useIdleRefocus({
			enabled: ref(true),
			intervalSeconds: ref(1),
			isDialogOpen: ref(true),
			onRefocus,
		})
		vi.advanceTimersByTime(5000)
		expect(onRefocus).not.toHaveBeenCalled()
	})

	it("does not steal focus from another text input", () => {
		const onRefocus = vi.fn()
		const input = document.createElement("input")
		document.body.appendChild(input)
		input.focus()
		expect(document.activeElement).toBe(input)
		useIdleRefocus({
			enabled: ref(true),
			intervalSeconds: ref(1),
			isDialogOpen: ref(false),
			onRefocus,
		})
		vi.advanceTimersByTime(3000)
		expect(onRefocus).not.toHaveBeenCalled()
	})

	it("re-evaluates the interval reactively", async () => {
		const onRefocus = vi.fn()
		const intervalSeconds = ref(10)
		useIdleRefocus({
			enabled: ref(true),
			intervalSeconds,
			isDialogOpen: ref(false),
			onRefocus,
		})
		// Shorten the interval; the watcher reschedules to the new value
		intervalSeconds.value = 1
		await Promise.resolve()
		vi.advanceTimersByTime(1000)
		expect(onRefocus).toHaveBeenCalledTimes(1)
	})
})
