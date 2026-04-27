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

// Vite injects these at build time. Tests run via Vitest's transform (no build),
// so define them on globalThis to keep modules that reference them happy.
if (typeof globalThis.__POS_TARGET__ === "undefined") {
	globalThis.__POS_TARGET__ = "web"
}
if (typeof globalThis.__FRAPPE_BASE_URL__ === "undefined") {
	globalThis.__FRAPPE_BASE_URL__ = ""
}
if (typeof globalThis.__SOCKETIO_PORT__ === "undefined") {
	globalThis.__SOCKETIO_PORT__ = 9000
}
if (typeof globalThis.__BUILD_VERSION__ === "undefined") {
	globalThis.__BUILD_VERSION__ = "test"
}

// Stub out the Tauri plugins so any module that lazy-imports them under a
// runtimeConfig branch resolves cleanly without trying to talk to the runtime.
vi.mock("@tauri-apps/plugin-http", () => ({
	fetch: vi.fn(async () => ({
		ok: true,
		status: 200,
		headers: { get: () => "application/json" },
		json: async () => ({ message: {} }),
		text: async () => "",
	})),
}))
vi.mock("@tauri-apps/plugin-stronghold", () => ({
	Stronghold: { load: vi.fn(async () => ({ save: vi.fn() })) },
}))
vi.mock("@tauri-apps/plugin-store", () => ({
	load: vi.fn(async () => ({
		get: vi.fn(async () => null),
		set: vi.fn(async () => {}),
		save: vi.fn(async () => {}),
	})),
}))
vi.mock("@tauri-apps/plugin-updater", () => ({
	check: vi.fn(async () => null),
}))
vi.mock("@tauri-apps/plugin-process", () => ({
	relaunch: vi.fn(async () => {}),
}))
vi.mock("@tauri-apps/api/path", () => ({
	appDataDir: vi.fn(async () => "/tmp"),
	join: vi.fn(async (...parts) => parts.join("/")),
}))

// Silence noisy console output unless a test wants it.
vi.spyOn(console, "debug").mockImplementation(() => {})
