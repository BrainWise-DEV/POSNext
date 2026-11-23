/**
 * D-R4-02: tax rules survive an offline start. They are cached when the server gives
 * them; a start without the server takes the cached ones (before: none, so every line
 * was taxed 0 and offline sales were collected short), and a failed reload never wipes
 * the rules the cart already has.
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const submit = vi.fn()
const stored = new Map()

vi.mock("frappe-ui", () => ({
	createResource: () => ({ submit, fetch: vi.fn(), reload: vi.fn(), data: null }),
	call: vi.fn(),
}))
vi.mock("@/utils/offline", () => ({ isOffline: () => true, getCachedItem: vi.fn() }))
vi.mock("@/utils/offline/db", () => ({
	getSetting: vi.fn(async (key, fallback = null) => (stored.has(key) ? stored.get(key) : fallback)),
	setSetting: vi.fn(async (key, value) => stored.set(key, value)),
}))
vi.mock("@/stores/serialNumber", () => ({
	useSerialNumberStore: () => ({ returnSerials: vi.fn() }),
}))

const { useInvoice } = await import("../useInvoice")

const VAT = [{ charge_type: "On Net Total", rate: 15, account_head: "VAT 15%" }]

describe("tax rules on an offline start (D-R4-02)", () => {
	beforeEach(() => {
		setActivePinia(createPinia())
		submit.mockReset()
		stored.clear()
	})

	it("an offline start takes the rules cached by the last online load", async () => {
		submit.mockResolvedValueOnce(VAT)
		await useInvoice().loadTaxRules("P1")

		submit.mockRejectedValueOnce(new TypeError("Failed to fetch"))
		const invoice = useInvoice()
		await invoice.loadTaxRules("P1")
		expect(invoice.taxRules.value).toEqual(VAT)
		expect(invoice.taxRulesNeedReload.value).toBe(true)
	})

	it("a failed reload keeps the rules the cart has", async () => {
		const invoice = useInvoice()
		submit.mockResolvedValueOnce(VAT)
		await invoice.loadTaxRules("P1")
		stored.clear()
		submit.mockRejectedValueOnce(new TypeError("Failed to fetch"))
		await invoice.loadTaxRules("P1")
		expect(invoice.taxRules.value).toEqual(VAT)
	})

	it("an online load clears the reload flag", async () => {
		const invoice = useInvoice()
		submit.mockRejectedValueOnce(new TypeError("Failed to fetch"))
		await invoice.loadTaxRules("P1")
		expect(invoice.taxRulesNeedReload.value).toBe(true)
		submit.mockResolvedValueOnce(VAT)
		await invoice.loadTaxRules("P1")
		expect(invoice.taxRulesNeedReload.value).toBe(false)
	})

	it("a late failure of an older load does not undo a newer one (review M3)", async () => {
		const invoice = useInvoice()
		stored.set("tax_rules:P1", [{ rate: 5, charge_type: "On Net Total" }])
		let failOld
		submit.mockImplementationOnce(() => new Promise((_, reject) => (failOld = reject)))
		submit.mockResolvedValueOnce(VAT)
		const older = invoice.loadTaxRules("P1")
		await invoice.loadTaxRules("P1")
		failOld(new TypeError("Failed to fetch"))
		await older
		expect(invoice.taxRules.value).toEqual(VAT)
		expect(invoice.taxRulesNeedReload.value).toBe(false)
	})
})
