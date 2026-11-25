/**
 * Reads of the offline cache straight from IndexedDB on the main thread, for when the
 * offline worker is unavailable (D-R4-02).
 *
 * The worker and the page share one IndexedDB database (`pos_next_offline`). When the
 * worker cannot start — e.g. its script cannot be fetched on an offline reload — its
 * graceful fallback used to answer every read with "nothing cached": an empty item
 * grid, "No payment methods available" and no offers, although the cache held them all.
 * These functions answer the same reads, with the worker's filters, from the page.
 */
import { db } from "./db";

function shown(item, showVariantsAsItems) {
	if (item.disabled) return false;
	return showVariantsAsItems ? !item.has_variants : !item.variant_of;
}

export async function cachedPaymentMethods(posProfile) {
	const table = db.table("payment_methods");
	return posProfile ? table.where("pos_profile").equals(posProfile).toArray() : table.toArray();
}

export async function cachedOffers(posProfile) {
	if (!posProfile) return [];
	const today = new Date().toISOString().split("T")[0];
	const offers = await db.table("offers").where("pos_profile").equals(posProfile).toArray();
	return offers.filter((offer) => !offer.valid_upto || offer.valid_upto >= today);
}

export async function cachedItemCount() {
	return db.table("items").count();
}

export async function cacheStats(showVariantsAsItems = false) {
	const { getOfflineInvoiceCount } = await import("./sync");
	const items = db.table("items");
	const [total, hidden, customers, lastSync, queuedInvoices] = await Promise.all([
		items.count(),
		items.filter((item) => (showVariantsAsItems ? !!item.has_variants : !!item.variant_of)).count(),
		db.table("customers").count(),
		db.table("settings").get("items_last_sync"),
		getOfflineInvoiceCount(),
	]);
	const count = total - hidden;
	return { items: count, customers, queuedInvoices, cacheReady: count > 0, lastSync: lastSync?.value || null };
}

export async function searchItems(searchTerm = "", limit = 50, offset = 0, showVariantsAsItems = false) {
	const term = String(searchTerm || "").toLowerCase().trim();
	const words = term.split(/\s+/).filter(Boolean);
	const matches = (item) =>
		words.every((word) =>
			[item.item_code, item.item_name, ...(item.barcodes || [])].some((field) =>
				String(field || "").toLowerCase().includes(word)
			)
		);
	return db
		.table("items")
		.orderBy("item_name")
		.filter((item) => shown(item, showVariantsAsItems) && (!words.length || matches(item)))
		.offset(offset)
		.limit(limit)
		.toArray();
}

export async function searchItemsByGroup(itemGroups = [], limit = 50, offset = 0, showVariantsAsItems = false) {
	if (!itemGroups?.length) return searchItems("", limit, offset, showVariantsAsItems);
	const groups = new Set(itemGroups);
	return db
		.table("items")
		.orderBy("item_name")
		.filter((item) => groups.has(item.item_group) && shown(item, showVariantsAsItems))
		.offset(offset)
		.limit(limit)
		.toArray();
}

export async function searchCustomers(searchTerm = "", limit = 20) {
	const term = String(searchTerm || "").toLowerCase();
	const customers = db.table("customers");
	if (!term) return limit > 0 ? customers.limit(limit).toArray() : customers.toArray();
	const all = await customers.toArray();
	return all
		.filter((c) =>
			[c.customer_name, c.mobile_no, c.name].some((field) => String(field || "").toLowerCase().includes(term))
		)
		.slice(0, limit || all.length);
}

/** The pending offline sales and their count, as the page's sync reads them (sync.js). */
export async function queuedInvoices() {
	const { getOfflineInvoices } = await import("./sync");
	return getOfflineInvoices();
}

export async function queuedInvoiceCount() {
	const { getOfflineInvoiceCount } = await import("./sync");
	return getOfflineInvoiceCount();
}

/**
 * Queue an offline sale as the worker does (SAVE_INVOICE): one row per offline_id, the
 * same cart paid again is not queued twice, and local stock is left to the sync.
 * Not sync.js's saveOfflineInvoice, which also deducts local stock: the worker does
 * not, and a sale must be queued the same way whichever side queues it.
 */
export async function queueInvoice(invoiceData) {
	if (!invoiceData?.items?.length) throw new Error("Cannot save empty invoice");
	const { queuedOfflineId } = await import("./uuid");
	const data = JSON.parse(JSON.stringify(invoiceData));
	const offlineId = queuedOfflineId(data);
	data.offline_id = offlineId;
	const queue = db.table("invoice_queue");
	const queued = async () => {
		const existing = await queue.where("offline_id").equals(offlineId).first();
		return existing ? { success: true, id: existing.id, offline_id: offlineId, duplicate: true } : null;
	};
	const already = await queued();
	if (already) return already;
	try {
		const id = await queue.add({ offline_id: offlineId, data, timestamp: Date.now(), synced: false, retry_count: 0 });
		return { success: true, id, offline_id: offlineId };
	} catch (error) {
		// The worker queued the same sale as it crashed (unique offline_id): it is queued
		if (error?.name === "ConstraintError") {
			const row = await queued();
			if (row) return row;
		}
		throw error;
	}
}
