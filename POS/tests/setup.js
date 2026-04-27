/**
 * Vitest global setup — runs before any test file.
 * Provides:
 *   - fake-indexeddb so Dexie has a working backend in jsdom
 *   - a stub `__()` translator so frappe-ui logs don't blow up
 */

import "fake-indexeddb/auto"
import { vi } from "vitest"

if (typeof globalThis.__ === "undefined") {
	globalThis.__ = (s, args = []) => {
		if (!args || args.length === 0) return s
		let i = 0
		return s.replace(/\{(\d+)\}/g, () => String(args[i++] ?? ""))
	}
}

if (typeof globalThis.crypto === "undefined") {
	const { webcrypto } = await import("node:crypto")
	globalThis.crypto = webcrypto
}

if (typeof globalThis.csrf_token === "undefined") {
	globalThis.csrf_token = "test-token"
}

// Silence noisy console output unless a test wants it.
vi.spyOn(console, "debug").mockImplementation(() => {})
