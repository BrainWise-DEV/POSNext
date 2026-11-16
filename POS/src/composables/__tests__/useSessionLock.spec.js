/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("@/utils/apiWrapper", () => ({ call: vi.fn() }))
vi.mock("@/data/user", () => ({
	userData: {
		getDisplayName: () => "Cashier",
		getImageUrl: () => null,
		getInitials: () => "C",
	},
}))
vi.mock("@/stores/posCart", () => ({
	usePOSCartStore: () => ({ isSubmitting: false }),
}))
vi.mock("@/utils/offline/offlineState", () => ({
	offlineState: { isOffline: false },
}))

import { useSessionLock } from "@/composables/useSessionLock"

describe("useSessionLock idle timer", () => {
	afterEach(() => {
		const { stopActivityTracking, clearLock } = useSessionLock()
		stopActivityTracking()
		clearLock()
		vi.useRealTimers()
	})

	it("locks after the timeout with no activity once tracking starts", () => {
		vi.useFakeTimers()
		const { configure, startActivityTracking, isLocked } = useSessionLock()
		configure({ enabled: true, timeoutMinutes: 1 })

		startActivityTracking()
		vi.advanceTimersByTime(60 * 1000)

		expect(isLocked.value).toBe(true)
	})
})

describe("useSessionLock without Web Crypto (dev mode over plain http)", () => {
	afterEach(() => vi.unstubAllGlobals())

	it("skips the offline unlock hash instead of failing the login", async () => {
		vi.stubGlobal("crypto", { getRandomValues: (a) => a })
		const { cachePasswordHashFromLogin } = useSessionLock()

		await expect(cachePasswordHashFromLogin("secret")).resolves.toBeUndefined()
	})
})
