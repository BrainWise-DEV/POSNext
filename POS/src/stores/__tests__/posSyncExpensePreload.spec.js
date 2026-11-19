/** Offline preload asks for expense dialog data only when the profile allows POS expenses. */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const call = vi.fn(async () => null)
const asyncNoop = () => vi.fn(async () => ({}))

vi.mock("@/utils/apiWrapper", () => ({ call }))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn() }),
}))
vi.mock("@/utils/logger", () => ({
	logger: { create: () => new Proxy({}, { get: () => vi.fn() }) },
}))
vi.mock("@/utils/offline/offlineState", () => ({
	offlineState: { isOffline: false, getConnectionQuality: () => "good", subscribe: vi.fn() },
}))
vi.mock("@/utils/offline/workerClient", () => ({
	offlineWorker: new Proxy({}, { get: () => vi.fn(async () => ({})) }),
}))
vi.mock("@/utils/offline", () => ({
	cacheCustomersFromServer: asyncNoop(),
	cachePaymentMethodsFromServer: asyncNoop(),
	cacheSalesPersonsFromServer: asyncNoop(),
	syncOfflineInvoices: asyncNoop(),
	syncOfflineExpenses: asyncNoop(),
	saveOfflineExpense: asyncNoop(),
	getPendingExpenses: vi.fn(async () => []),
	getPendingExpenseCount: vi.fn(async () => 0),
	deleteOfflineExpense: asyncNoop(),
	discardOfflineExpenseAttachments: asyncNoop(),
	cacheExpenseDialogData: asyncNoop(),
	cacheInvoiceHistory: asyncNoop(),
	cacheUnpaidInvoices: asyncNoop(),
	cacheUnpaidSummary: asyncNoop(),
}))

globalThis.__ = (s) => s

const { usePOSSyncStore } = await import("../posSync")
const EXPENSE_METHOD = "pos_next.api.expenses.get_expense_dialog_data"

describe("posSync offline preload: expense dialog data", () => {
	beforeEach(() => {
		setActivePinia(createPinia())
		call.mockClear()
	})

	it("skips the expense call when POS expense is disabled on the profile", async () => {
		await usePOSSyncStore().preloadDataForOffline({ name: "P", posa_allow_pos_expense: 0 }, "SHIFT-1")

		expect(call.mock.calls.map(([method]) => method)).not.toContain(EXPENSE_METHOD)
	})

	it("loads expense dialog data when POS expense is enabled", async () => {
		await usePOSSyncStore().preloadDataForOffline({ name: "P", posa_allow_pos_expense: 1 }, "SHIFT-1")

		expect(call.mock.calls.map(([method]) => method)).toContain(EXPENSE_METHOD)
	})
})
