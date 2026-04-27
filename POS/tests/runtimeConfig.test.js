import { afterEach, describe, expect, it, vi } from "vitest"

describe("runtimeConfig", () => {
	afterEach(() => {
		vi.resetModules()
		globalThis.__POS_TARGET__ = "web"
		globalThis.__FRAPPE_BASE_URL__ = ""
	})

	it("defaults to web mode with same-origin paths", async () => {
		globalThis.__POS_TARGET__ = "web"
		globalThis.__FRAPPE_BASE_URL__ = ""
		const mod = await import("@/utils/runtimeConfig")
		expect(mod.runtimeConfig.target).toBe("web")
		expect(mod.runtimeConfig.isDesktop).toBe(false)
		expect(mod.runtimeConfig.useRustTransport).toBe(false)
		expect(mod.runtimeConfig.hasRealtime).toBe(true)
		expect(mod.runtimeConfig.hasServiceWorker).toBe(true)
		expect(mod.apiUrl("/api/method/foo")).toBe("/api/method/foo")
	})

	it("flips to desktop mode and prepends the configured base URL", async () => {
		globalThis.__POS_TARGET__ = "desktop"
		globalThis.__FRAPPE_BASE_URL__ = "https://acme.frappe.cloud"
		const mod = await import("@/utils/runtimeConfig")
		expect(mod.runtimeConfig.target).toBe("desktop")
		expect(mod.runtimeConfig.isDesktop).toBe(true)
		expect(mod.runtimeConfig.useRustTransport).toBe(true)
		expect(mod.runtimeConfig.hasRealtime).toBe(false)
		expect(mod.runtimeConfig.hasServiceWorker).toBe(false)
		expect(mod.apiUrl("/api/method/foo")).toBe(
			"https://acme.frappe.cloud/api/method/foo",
		)
		expect(mod.apiUrl("api/method/bar")).toBe(
			"https://acme.frappe.cloud/api/method/bar",
		)
		expect(mod.apiUrl("https://other/x")).toBe("https://other/x")
	})

	it("strips a trailing slash from the base URL", async () => {
		globalThis.__POS_TARGET__ = "desktop"
		globalThis.__FRAPPE_BASE_URL__ = "https://acme.frappe.cloud/"
		const mod = await import("@/utils/runtimeConfig")
		expect(mod.runtimeConfig.baseUrl).toBe("https://acme.frappe.cloud")
		expect(mod.apiUrl("/api/method/foo")).toBe(
			"https://acme.frappe.cloud/api/method/foo",
		)
	})

	it("caches and clears the API auth header", async () => {
		globalThis.__POS_TARGET__ = "desktop"
		globalThis.__FRAPPE_BASE_URL__ = "https://acme.frappe.cloud"
		const mod = await import("@/utils/runtimeConfig")
		expect(mod.getAuthHeader()).toBeNull()
		mod.setApiCredentials({ apiKey: "k", apiSecret: "s" })
		expect(mod.getAuthHeader()).toBe("token k:s")
		mod.clearApiCredentials()
		expect(mod.getAuthHeader()).toBeNull()
		mod.setApiCredentials({ apiKey: null })
		expect(mod.getAuthHeader()).toBeNull()
	})
})
