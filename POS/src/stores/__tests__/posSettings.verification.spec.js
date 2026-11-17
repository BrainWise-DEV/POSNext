/** Customer verification getters on the POS settings store. */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("frappe-ui", () => ({ createResource: () => ({ submit: vi.fn() }) }))
vi.mock("../bootstrap", () => ({ useBootstrapStore: () => ({ getPreloadedPOSSettings: () => null }) }))

globalThis.__ = (s) => s

const { usePOSSettingsStore } = await import("../posSettings")

describe("posSettings verification getters", () => {
	let store
	beforeEach(() => {
		setActivePinia(createPinia())
		store = usePOSSettingsStore()
	})

	it("defaults requireSplitName to false and placeholderEmailDomain to empty", () => {
		expect(store.requireSplitName).toBe(false)
		expect(store.placeholderEmailDomain).toBe("")
	})

	it("reflects settings values", () => {
		store.settings.require_split_name = 1
		store.settings.placeholder_email_domain = "example.test"
		expect(store.requireSplitName).toBe(true)
		expect(store.placeholderEmailDomain).toBe("example.test")
	})

	it("no longer exposes the client-named flag", () => {
		expect("miraayaInstalled" in store).toBe(false)
		expect("miraaya_installed" in store.settings).toBe(false)
	})
})
