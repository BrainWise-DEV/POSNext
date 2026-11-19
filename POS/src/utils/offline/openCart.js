/**
 * The open POS cart, kept in IndexedDB so a reload or a browser crash does not lose
 * it (D-4). One slot per browser tab in the offline `settings` table, so no schema
 * change. The tab id lives in sessionStorage: F5 keeps it and brings the tab's own
 * cart back; a new tab gets a new id and starts empty (Ruling 136 (e)).
 *
 * The record has the shape of a held draft (posDrafts.saveDraftInvoice: pos_profile,
 * customer, items, applied_offers, applied_coupon), plus the cart state a draft does
 * not keep and the scope (user, POS Profile, opening shift) it belongs to.
 *
 * Every call is chained, so a save still in flight can never land after the delete
 * that followed it, and bounded by a timeout, so a storage call that never settles
 * cannot hang logout, shift close or boot (after one timeout, storage is skipped for
 * the rest of the page load). Storage errors are logged and swallowed:
 * without storage the POS works as before, only without the reload safety net.
 */
import * as offlineDb from "./db";
import { generateUUID } from "./uuid";

export const OPEN_CART_PREFIX = "pos_open_cart::";
export const OPEN_CART_TAB_KEY = "pos_open_cart_tab";
export const OPEN_CART_TIMEOUT_MS = 2000;

let chain = Promise.resolve();
let fallbackTabId = null; // sessionStorage unavailable: one id for this page load
// A call that timed out leaves IndexedDB stalled: later calls fail fast for this page load.
let stalled = false;

function enqueue(operation, fallback) {
	const run = chain.then(async () => {
		if (stalled) return fallback;
		let timer = null;
		try {
			const timeout = new Promise((_, reject) => {
				timer = setTimeout(() => {
					stalled = true;
					reject(new Error("Open cart storage timed out"));
				}, OPEN_CART_TIMEOUT_MS);
			});
			return await Promise.race([operation(), timeout]);
		} catch (error) {
			console.warn("Open cart storage is unavailable:", error);
			return fallback;
		} finally {
			clearTimeout(timer);
		}
	});
	chain = run;
	return run;
}

/** Use storage again after a stall (tests; a stalled page otherwise stays off until reload). */
export function resetOpenCartStorage() {
	stalled = false;
	chain = Promise.resolve();
}

/** This tab's id: kept across F5 in sessionStorage, new for a new tab. */
export function openCartTabId() {
	try {
		let id = globalThis.sessionStorage?.getItem(OPEN_CART_TAB_KEY);
		if (!id) {
			id = generateUUID();
			globalThis.sessionStorage.setItem(OPEN_CART_TAB_KEY, id);
		}
		return id;
	} catch {
		fallbackTabId = fallbackTabId || generateUUID();
		return fallbackTabId;
	}
}

/** The settings key of this tab's slot. */
export function openCartSlotKey() {
	return `${OPEN_CART_PREFIX}${openCartTabId()}`;
}

/** The scope a saved cart belongs to: one user, one POS Profile, one opening shift. */
export function openCartScopeKey(scope) {
	if (!scope?.user || !scope?.pos_profile || !scope?.pos_opening_shift) return null;
	return [scope.user, scope.pos_profile, scope.pos_opening_shift].join("::");
}

/** This tab's saved cart, or null. */
export function readOpenCart() {
	return enqueue(async () => (await offlineDb.db.settings.get(openCartSlotKey()))?.value || null, null);
}

/** Replace this tab's saved cart. */
export function writeOpenCart(record) {
	return enqueue(async () => {
		// Vue proxies cannot be stored: plain JSON, as drafts are saved.
		const value = JSON.parse(JSON.stringify(record));
		await offlineDb.db.settings.put({ key: openCartSlotKey(), value });
		return true;
	}, false);
}

/** Forget this tab's saved cart. */
export function deleteOpenCart() {
	return enqueue(async () => {
		await offlineDb.db.settings.delete(openCartSlotKey());
		return true;
	}, false);
}

/**
 * Forget the saved carts of every tab: all of them (shift close, logout), or those
 * not saved for `keepScopeKey` (another user, POS Profile or shift: never restorable).
 */
export function deleteOpenCarts(keepScopeKey = null) {
	return enqueue(async () => {
		const rows = await offlineDb.db.settings.toArray();
		const keys = rows
			.filter((row) => String(row?.key || "").startsWith(OPEN_CART_PREFIX))
			.filter((row) => !keepScopeKey || openCartScopeKey(row.value?.scope) !== keepScopeKey)
			.map((row) => row.key);
		if (keys.length) await offlineDb.db.settings.bulkDelete(keys);
		return true;
	}, false);
}
