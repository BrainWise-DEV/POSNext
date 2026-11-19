/**
 * Sales persons list for the item-level picker (EditItemDialog).
 *
 * Online: fetched from the server once per POS Profile per session and kept in
 * memory, instead of on every dialog open.
 * Offline, or when the server call fails: the IndexedDB copy maintained by
 * posSync / PaymentDialog. A failed or offline load is not memoised, so the
 * next open retries the server.
 */
import { call } from "@/utils/apiWrapper";
import { isOffline } from "@/utils/offline/offlineState";

const sessionCache = new Map();

async function readOfflineCopy(posProfile) {
	try {
		const { getCachedSalesPersons } = await import("@/utils/offline/cache");
		return (await getCachedSalesPersons(posProfile)) || [];
	} catch {
		return [];
	}
}

async function fetchFromServer(posProfile) {
	try {
		const result = await call("pos_next.api.pos_profile.get_sales_persons", {
			pos_profile: posProfile,
		});
		return result?.message || result || [];
	} catch (error) {
		sessionCache.delete(posProfile);
		console.error("Failed to load sales persons:", error);
		return readOfflineCopy(posProfile);
	}
}

/**
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<Array>} sales persons (name, sales_person_name, commission_rate, employee)
 */
export function loadSalesPersonsForProfile(posProfile) {
	if (!posProfile) return Promise.resolve([]);
	if (sessionCache.has(posProfile)) return sessionCache.get(posProfile);
	if (isOffline()) return readOfflineCopy(posProfile);

	const pending = fetchFromServer(posProfile);
	sessionCache.set(posProfile, pending);
	return pending;
}

/** Forget the in-memory list (e.g. after a POS Profile switch or in tests). */
export function clearSalesPersonsSessionCache() {
	sessionCache.clear();
}
