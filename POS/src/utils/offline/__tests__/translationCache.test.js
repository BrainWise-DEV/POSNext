import { beforeEach, describe, expect, it, vi } from "vitest"

const stored = new Map()

vi.mock("../db", () => ({
	db: {
		translations: {
			get: vi.fn(async (locale) => stored.get(locale)),
			put: vi.fn(async (entry) => stored.set(entry.locale, entry)),
		},
	},
}))

const { translationCache, CACHE_VERSION } = await import("../translationCache")

describe("translationCache version", () => {
	beforeEach(() => stored.clear())

	it("refetches bundles cached before the current version", async () => {
		stored.set("ar", { locale: "ar", messages: { Clear: "واضح" }, timestamp: Date.now() })
		const old = await translationCache.get("ar")
		expect(translationCache.isStale(old.timestamp)).toBe(true)
		const entry = await translationCache.getFresh("ar", async () => ({ Clear: "مسح" }))
		expect(entry.messages.Clear).toBe("مسح")
	})

	it("keeps an older bundle as the offline fallback", async () => {
		stored.set("id", { locale: "id", messages: { Clear: "Hapus" }, timestamp: Date.now() })
		const entry = await translationCache.getFresh("id", async () => null)
		expect(entry.messages.Clear).toBe("Hapus")
	})

	it("serves bundles cached under the current version", async () => {
		await translationCache.set("en", { Clear: "Clear" })
		expect(stored.get("en").version).toBe(CACHE_VERSION)
		expect((await translationCache.get("en")).messages.Clear).toBe("Clear")
	})
})
