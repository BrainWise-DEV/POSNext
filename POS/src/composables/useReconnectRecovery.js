import { watch } from "vue";

/**
 * Back online after an offline start, the till reloads what it could only take from the
 * offline cache, or not at all (D-R4-02): the tax rules, the offer list (then the cart
 * is re-priced) and an empty item grid. Before, only an online F5 recovered them.
 *
 * @param {Object} deps
 * @param {() => boolean} deps.isOffline - reactive offline state
 * @param {() => boolean} deps.isReady - the POS finished its start (a shift is open)
 * @param {Object} deps.cart - cart store: taxRulesNeedReload, loadTaxRules, forceRefreshOffers
 * @param {Object} deps.offers - offers store: offersFromCache, refreshOffers
 * @param {Object} deps.items - item store: allItems, loadAllItems
 * @param {() => string} deps.profileName
 * @param {() => Object} deps.settings - POS Settings (tax_inclusive)
 * @param {Object} [deps.worker] - the offline worker client: started again if it gave up
 * @returns {{ recover: () => Promise<void> }}
 */
export function useReconnectRecovery({ isOffline, isReady, cart, offers, items, profileName, settings, worker }) {
	// One recovery at a time (review M3); a reconnect that comes while one runs is not
	// dropped: the recovery runs once more after it (review R1-m2)
	let running = null;
	let again = false;
	function recover() {
		if (running) {
			again = true;
			return running;
		}
		running = (async () => {
			do {
				again = false;
				await runRecovery();
			} while (again);
		})().finally(() => {
			running = null;
		});
		return running;
	}

	async function runRecovery() {
		const profile = profileName();
		if (!profile) return;
		// First: what follows rewrites the offline cache, which only a live worker can
		if (worker?.workerCrashed) await worker.revive().catch(() => false);
		const tasks = [];
		if (cart.taxRulesNeedReload) tasks.push(cart.loadTaxRules(profile, settings()));
		if (offers.offersFromCache) {
			tasks.push(offers.refreshOffers(profile).then((fetched) => fetched && cart.forceRefreshOffers()));
		}
		if (!(items.allItems?.length > 0)) tasks.push(items.loadAllItems(profile));
		await Promise.allSettled(tasks);
	}

	watch(isOffline, (offline, wasOffline) => {
		if (offline || !wasOffline || !isReady()) return;
		recover();
	});

	return { recover };
}
