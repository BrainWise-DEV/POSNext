/**
 * D-R4-04: a print format error reaches the cashier with its reason, not as a silent
 * failure or a "check QZ Tray" hint.
 */
import { describe, expect, it, vi } from "vitest"

vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? s.replace(/\{(\d+)\}/g, (_, i) => args[i]) : s)
})
vi.mock("@/utils/apiWrapper", () => ({ call: vi.fn() }))
vi.mock("@/utils/qzTray", () => ({ printHTML: vi.fn() }))
vi.mock("@/stores/posSettings", () => ({ usePOSSettingsStore: () => ({}) }))
vi.mock("@/utils/offline/workerClient", () => ({ offlineWorker: {} }))
vi.mock("@/utils/offline/sync", () => ({ getOfflineInvoiceByOfflineId: vi.fn() }))

const { eodPrintFailureMessage } = await import("../printEod")

describe("EOD print failure", () => {
	it("names the server's reason", () => {
		const error = {
			exc_type: "PrintFormatError",
			httpStatus: 417,
			messages: ["Error in print format on line 41: (1054, \"Unknown column 'address' in 'SELECT'\")"],
		}
		expect(eodPrintFailureMessage(error)).toBe(
			"EOD report did not print: Error in print format on line 41: (1054, \"Unknown column 'address' in 'SELECT'\")"
		)
	})

	it("falls back to the retry hint when there is no reason", () => {
		expect(eodPrintFailureMessage(null)).toBe("EOD report did not print. Use the Reprint button to retry.")
	})
})
