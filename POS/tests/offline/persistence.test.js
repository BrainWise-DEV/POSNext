/**
 * Tests for utils/offline/persistence.js — the navigator.storage.persist
 * wrapper that asks the browser not to evict our IndexedDB.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
	ensurePersistentStorage,
	getPersistenceStatus,
	requestPersistentStorage,
} from "@/utils/offline/persistence"

const persistMock = vi.fn()
const persistedMock = vi.fn()
const estimateMock = vi.fn()

function installStorageAPI() {
	Object.defineProperty(globalThis.navigator, "storage", {
		configurable: true,
		value: {
			persist: persistMock,
			persisted: persistedMock,
			estimate: estimateMock,
		},
	})
}

function uninstallStorageAPI() {
	Object.defineProperty(globalThis.navigator, "storage", {
		configurable: true,
		value: undefined,
	})
}

describe("offline/persistence", () => {
	beforeEach(() => {
		persistMock.mockReset()
		persistedMock.mockReset()
		estimateMock.mockReset()
	})

	afterEach(() => {
		uninstallStorageAPI()
	})

	it("reports unsupported when navigator.storage is missing", async () => {
		uninstallStorageAPI()
		const status = await getPersistenceStatus()
		expect(status).toEqual({
			supported: false,
			persisted: false,
			quota: null,
			usage: null,
		})
	})

	it("returns existing grant without calling persist()", async () => {
		installStorageAPI()
		persistedMock.mockResolvedValue(true)
		estimateMock.mockResolvedValue({ quota: 100, usage: 10 })

		const status = await ensurePersistentStorage()

		expect(persistMock).not.toHaveBeenCalled()
		expect(status).toMatchObject({
			supported: true,
			persisted: true,
			quota: 100,
			usage: 10,
		})
	})

	it("calls persist() when not yet granted, surfaces the result", async () => {
		installStorageAPI()
		// Initial check: not persisted; after persist(): persisted.
		persistedMock.mockResolvedValueOnce(false).mockResolvedValueOnce(true)
		persistMock.mockResolvedValue(true)
		estimateMock.mockResolvedValue({ quota: 200, usage: 20 })

		const status = await requestPersistentStorage()

		expect(persistMock).toHaveBeenCalledOnce()
		expect(status.persisted).toBe(true)
	})

	it("survives persist() rejection", async () => {
		installStorageAPI()
		persistedMock.mockResolvedValue(false)
		persistMock.mockRejectedValue(new Error("user gesture required"))
		estimateMock.mockResolvedValue({ quota: null, usage: null })

		const status = await requestPersistentStorage()
		expect(status.persisted).toBe(false)
		// Did not throw — that's the contract.
	})

	it("returns false unsupported result when ensurePersistentStorage runs without API", async () => {
		uninstallStorageAPI()
		const status = await ensurePersistentStorage()
		expect(status).toMatchObject({ supported: false, persisted: false })
	})
})
