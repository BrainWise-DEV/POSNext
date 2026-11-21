/**
 * D-R2-17: a one-time offer the customer already used is named to the cashier,
 * instead of the cart silently showing the list price.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? s.replace(/{(\d+)}/g, (m, n) => args[n]) : s)
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({})),
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn() }),
}))
vi.mock("@/utils/offline", () => ({ isOffline: () => false }))
vi.mock("@/utils/offline/workerClient", () => ({ offlineWorker: {} }))
vi.mock("@/utils/offline/db", () => ({
	getOneTimeRedemptions: vi.fn(),
	setOneTimeRedemptions: vi.fn(),
	addOneTimeRedemptions: vi.fn(),
}))

const { usePOSOffersStore } = await import("../posOffers")

const c40 = { name: "UIT-PR-C40", title: "C 40%", auto: 1, one_time_per_customer: 1, apply_on: "Item Code", eligible_items: ["UIT-C"] }
const other = { name: "UIT-PR-OTHER", title: "Other", auto: 1, one_time_per_customer: 1, apply_on: "Item Code", eligible_items: ["UIT-Z"] }

describe("D-R2-17: a used one-time offer is named", () => {
	let offers
	beforeEach(() => {
		setActivePinia(createPinia())
		offers = usePOSOffersStore()
		offers.setAvailableOffers([c40, other])
		offers.updateCartSnapshot({ itemCount: 1, itemCodes: ["UIT-C"], subtotal: 50, itemQuantities: { "UIT-C": 1 } })
	})

	it("lists the offer the cart would get, but this customer already used", () => {
		offers.setOneTimeContext({ identified: true, redeemedRules: ["UIT-PR-C40", "UIT-PR-OTHER"] })
		expect(offers.usedOneTimeOffers.map((o) => o.name)).toEqual(["UIT-PR-C40"])
	})

	it("lists nothing before the offer is used", () => {
		offers.setOneTimeContext({ identified: true, redeemedRules: [] })
		expect(offers.usedOneTimeOffers).toEqual([])
	})

	it("lists nothing for the walk-in customer (asked to select a customer instead)", () => {
		offers.setOneTimeContext({ identified: false, redeemedRules: ["UIT-PR-C40"] })
		expect(offers.usedOneTimeOffers).toEqual([])
	})
})
