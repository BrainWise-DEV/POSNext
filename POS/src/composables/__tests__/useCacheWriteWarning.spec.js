/**
 * Review R1-m3: the lost-cache-write warning listener goes with the POS page: once it is
 * unmounted, the event warns nobody (and a remount does not warn twice).
 * @vitest-environment jsdom
 */
import { mount } from "@vue/test-utils"
import { defineComponent, h } from "vue"
import { describe, expect, it, vi } from "vitest"

vi.hoisted(() => {
	globalThis.__ = (s) => s
})
vi.mock("@/utils/offline/workerClient", () => ({ CACHE_WRITE_FAILED_EVENT: "posnext:offline-cache-write-failed" }))

const { useCacheWriteWarning } = await import("../useCacheWriteWarning")

const fire = () => window.dispatchEvent(new CustomEvent("posnext:offline-cache-write-failed"))

function page(showWarning) {
	return mount(
		defineComponent({
			setup() {
				useCacheWriteWarning(showWarning)
				return () => h("div")
			},
		})
	)
}

describe("lost cache write warning (R1-m3)", () => {
	it("warns while the page is mounted, and not after it is unmounted", () => {
		const showWarning = vi.fn()
		const wrapper = page(showWarning)
		fire()
		expect(showWarning).toHaveBeenCalledTimes(1)
		wrapper.unmount()
		const later = vi.fn()
		const again = page(later)
		fire()
		expect(showWarning).toHaveBeenCalledTimes(1) // the unmounted page's listener is gone
		expect(later).toHaveBeenCalledTimes(1)
		again.unmount()
	})
})
