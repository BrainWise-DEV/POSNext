/**
 * D-R4-02: back online after an offline start, the till reloads what it had only from
 * the cache (or not at all) without an F5: tax rules, the offer list (and re-prices the
 * cart) and an empty item grid.
 */
import { nextTick, reactive } from "vue"
import { describe, expect, it, vi } from "vitest"
import { useReconnectRecovery } from "../useReconnectRecovery"

function setup({ taxRulesNeedReload = true, offersFromCache = true, allItems = [], worker = null } = {}) {
	const state = reactive({ offline: true, ready: true })
	const cart = { taxRulesNeedReload, loadTaxRules: vi.fn(async () => []), forceRefreshOffers: vi.fn() }
	const offers = { offersFromCache, refreshOffers: vi.fn(async () => true) }
	const items = { allItems, loadAllItems: vi.fn(async () => {}) }
	useReconnectRecovery({
		isOffline: () => state.offline,
		isReady: () => state.ready,
		cart,
		offers,
		items,
		profileName: () => "P1",
		settings: () => ({ tax_inclusive: 0 }),
		worker,
	})
	return { state, cart, offers, items }
}

const flush = async () => {
	await nextTick()
	await new Promise((r) => setTimeout(r, 0))
}

describe("reconnect recovery", () => {
	it("reloads tax rules, offers (then re-prices) and an empty item grid", async () => {
		const { state, cart, offers, items } = setup()
		state.offline = false
		await flush()
		expect(cart.loadTaxRules).toHaveBeenCalledWith("P1", { tax_inclusive: 0 })
		expect(offers.refreshOffers).toHaveBeenCalledWith("P1")
		expect(cart.forceRefreshOffers).toHaveBeenCalled()
		expect(items.loadAllItems).toHaveBeenCalledWith("P1")
	})

	it("starts a worker that gave up again before rewriting the cache (review I-1)", async () => {
		const order = []
		const worker = { workerCrashed: true, revive: vi.fn(async () => order.push("revive") && true) }
		const { state, offers } = setup({ worker })
		offers.refreshOffers.mockImplementation(async () => order.push("offers") && true)
		state.offline = false
		await flush()
		expect(worker.revive).toHaveBeenCalled()
		expect(order[0]).toBe("revive")
	})

	it("leaves alone what the server already gave", async () => {
		const { state, cart, offers, items } = setup({
			taxRulesNeedReload: false,
			offersFromCache: false,
			allItems: [{ item_code: "A" }],
		})
		state.offline = false
		await flush()
		expect(cart.loadTaxRules).not.toHaveBeenCalled()
		expect(offers.refreshOffers).not.toHaveBeenCalled()
		expect(items.loadAllItems).not.toHaveBeenCalled()
	})

	it("does nothing before the POS has started", async () => {
		const { state, cart } = setup()
		state.ready = false
		state.offline = false
		await flush()
		expect(cart.loadTaxRules).not.toHaveBeenCalled()
	})

	it("overlapping recoveries never run at once (review M3)", async () => {
		const { cart } = setup()
		const finishers = []
		cart.loadTaxRules.mockImplementation(() => new Promise((resolve) => finishers.push(resolve)))
		const recovery = useReconnectRecovery({
			isOffline: () => false,
			isReady: () => true,
			cart,
			offers: { offersFromCache: false, refreshOffers: vi.fn() },
			items: { allItems: [{}], loadAllItems: vi.fn() },
			profileName: () => "P1",
			settings: () => ({}),
		})
		const first = recovery.recover()
		const second = recovery.recover()
		await flush()
		expect(cart.loadTaxRules).toHaveBeenCalledTimes(1) // the second waits for the first
		while (finishers.length) {
			finishers.shift()([])
			await flush()
		}
		await Promise.all([first, second])
	})

	it("a reconnect during a running recovery runs it again after (review R1-m2)", async () => {
		const { cart } = setup()
		const finishers = []
		cart.loadTaxRules.mockImplementation(() => new Promise((resolve) => finishers.push(resolve)))
		const recovery = useReconnectRecovery({
			isOffline: () => false,
			isReady: () => true,
			cart,
			offers: { offersFromCache: false, refreshOffers: vi.fn() },
			items: { allItems: [{}], loadAllItems: vi.fn() },
			profileName: () => "P1",
			settings: () => ({}),
		})
		const first = recovery.recover()
		const second = recovery.recover() // a reconnect while the first still runs
		finishers.shift()([])
		await flush()
		expect(cart.loadTaxRules).toHaveBeenCalledTimes(2)
		finishers.shift()([])
		await Promise.all([first, second])
		expect(cart.loadTaxRules).toHaveBeenCalledTimes(2)
	})
})
