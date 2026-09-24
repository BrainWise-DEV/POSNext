import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const returnSerials = vi.fn()
const draft = {
	draft_id: "D-1",
	items: [
		{ item_code: "SER-1", has_serial_no: 1, serial_no: "SN-1\nSN-2" },
		{ item_code: "PLAIN", has_serial_no: 0 },
	],
}

vi.mock("@/stores/serialNumber", () => ({
	useSerialNumberStore: () => ({ returnSerials }),
}))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({
		showSuccess: vi.fn(),
		showError: vi.fn(),
		showWarning: vi.fn(),
	}),
}))
vi.mock("@/utils/draftManager", () => ({
	deleteDraft: vi.fn(async () => true),
	getAllDrafts: vi.fn(async () => [draft]),
	getDraftsCount: vi.fn(async () => 1),
	saveDraft: vi.fn(),
	updateDraft: vi.fn(),
}))

globalThis.__ = (s) => s

const { usePOSDraftsStore } = await import("../posDrafts")

describe("posDrafts serial release", () => {
	beforeEach(async () => {
		setActivePinia(createPinia())
		returnSerials.mockClear()
	})

	it("returns a discarded draft's serials to the cache", async () => {
		const store = usePOSDraftsStore()
		await store.loadDrafts()
		await store.deleteDraft("D-1", { returnSerials: true })
		expect(returnSerials).toHaveBeenCalledTimes(1)
		expect(returnSerials).toHaveBeenCalledWith("SER-1", "SN-1\nSN-2")
	})

	it("keeps serials consumed when the draft was sold", async () => {
		const store = usePOSDraftsStore()
		await store.loadDrafts()
		await store.deleteDraft("D-1")
		expect(returnSerials).not.toHaveBeenCalled()
	})
})
