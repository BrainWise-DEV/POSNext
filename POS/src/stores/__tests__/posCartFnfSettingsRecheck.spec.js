/**
 * D-R2-03: an eligibility answer that comes from the F&F Settings (program off, no
 * approved domains) is not kept for the customer: the next cart change asks again.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const api = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
	globalThis.window.posnext_app_flags = { posnext_promotions: 1 }
	return { eligibility: [] }
})
const ELIGIBILITY = "posnext_promotions.api.friends_and_family.check_friends_and_family_eligibility"
vi.mock("frappe-ui", () => ({
	call: vi.fn(async (method) => (method === ELIGIBILITY ? api.eligibility.shift() : {})),
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn() }),
}))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock("@/utils/offline", () => ({
	isOffline: () => false,
	getCachedItem: vi.fn(),
}))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { call } = await import("frappe-ui")
const { usePOSCartStore } = await import("../posCart")

const eligibilityCalls = () => call.mock.calls.filter(([method]) => method === ELIGIBILITY).length

describe("D-R2-03: F&F eligibility follows the settings", () => {
	let cart
	beforeEach(() => {
		call.mockClear()
		setActivePinia(createPinia())
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = { name: "CUST-FNF" }
	})

	it("a program_inactive answer is asked again on the next evaluation", async () => {
		api.eligibility = [
			{ eligible: false, reason: "program_inactive" },
			{ eligible: true, reason: "applied", discount_percentage: 30 },
		]
		await cart.refreshFriendsAndFamilyEligibility(true)
		expect(cart.fnfEligibility.reason).toBe("program_inactive")
		// The offer pass of the next cart change asks without force
		await cart.refreshFriendsAndFamilyEligibility()
		expect(eligibilityCalls()).toBe(2)
		expect(cart.fnfEligibility.eligible).toBe(true)
		expect(cart.fnfEligibility.discountPercentage).toBe(30)
	})

	it("no_approved_domains is asked again too", async () => {
		api.eligibility = [
			{ eligible: false, reason: "no_approved_domains" },
			{ eligible: true, reason: "applied", discount_percentage: 30 },
		]
		await cart.refreshFriendsAndFamilyEligibility(true)
		await cart.refreshFriendsAndFamilyEligibility()
		expect(cart.fnfEligibility.eligible).toBe(true)
	})

	it("an answer about the customer stays cached", async () => {
		api.eligibility = [{ eligible: false, reason: "customer_ineligible" }]
		await cart.refreshFriendsAndFamilyEligibility(true)
		await cart.refreshFriendsAndFamilyEligibility()
		expect(eligibilityCalls()).toBe(1)
		expect(cart.fnfEligibility.reason).toBe("customer_ineligible")
	})
})
