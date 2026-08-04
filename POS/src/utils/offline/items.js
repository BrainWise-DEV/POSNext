import { db, getSetting, setSetting } from "./db";

// Cache items in IndexedDB
export const cacheItems = async (items, priceList = null) => {
	try {
		if (!items || items.length === 0) return;

		// Process items with barcodes
		const processedItems = items.map((item) => ({
			...item,
			barcodes: item.item_barcode
				? Array.isArray(item.item_barcode)
					? item.item_barcode.map((b) => b.barcode).filter(Boolean)
					: [item.item_barcode]
				: [],
		}));

		// Save to items table
		await db.items.bulkPut(processedItems);

		// Save prices if price list is provided
		if (priceList) {
			const prices = items.map((item) => ({
				price_list: priceList,
				item_code: item.item_code,
				rate: item.rate || item.price_list_rate || 0,
				timestamp: Date.now(),
			}));
			await db.item_prices.bulkPut(prices);
		}

		// Update last sync time
		await setSetting("items_last_sync", Date.now());

		console.log(`Cached ${items.length} items`);
		return true;
	} catch (error) {
		console.error("Error caching items:", error);
		return false;
	}
};

// Get cached items
export const getCachedItems = async (limit = 100) => {
	try {
		const items = await db.items.limit(limit).toArray();
		return items;
	} catch (error) {
		console.error("Error getting cached items:", error);
		return [];
	}
};

// Fuzzy search: matches if any search word is contained in item text
export const searchCachedItems = async (searchTerm, limit = 50) => {
	try {
		if (!searchTerm) {
			return await db.items.limit(limit).toArray();
		}

		const term = searchTerm.toLowerCase().trim();
		const searchWords = term.split(/\s+/).filter(Boolean);
		const allItems = await db.items.limit(limit * 10).toArray();

		// Filter and score items
		const results = allItems
			.map((item) => {
				const searchable = `${item.item_code || ""} ${item.item_name || ""} ${
					item.description || ""
				}`.toLowerCase();

				// Word-order independent: all words must appear somewhere
				if (!searchWords.every((word) => searchable.includes(word))) return null;

				// Score: prefer exact and prefix matches
				let score = 0;
				if (item.item_name?.toLowerCase() === term) score = 1000;
				else if (item.item_code?.toLowerCase() === term) score = 900;
				else if (item.item_name?.toLowerCase().startsWith(term)) score = 500;
				else if (item.item_code?.toLowerCase().startsWith(term)) score = 400;
				else score = 100;

				return { item, score };
			})
			.filter(Boolean)
			.sort((a, b) => b.score - a.score)
			.slice(0, limit)
			.map(({ item }) => item);

		return results;
	} catch (error) {
		console.error("Error searching cached items:", error);
		return [];
	}
};

// Get item by barcode
export const getItemByBarcode = async (barcode) => {
	try {
		const item = await db.items.where("barcodes").equals(barcode).first();
		return item;
	} catch (error) {
		console.error("Error getting item by barcode:", error);
		return null;
	}
};

// Get cached variants for a template item
export const getCachedVariants = async (templateItemCode) => {
	try {
		if (!templateItemCode) return [];

		// Query items where variant_of equals the template item code
		const variants = await db.items.where("variant_of").equals(templateItemCode).toArray();

		return variants;
	} catch (error) {
		console.error("Error getting cached variants:", error);
		return [];
	}
};

// Get cached batch data for an item
export const getCachedBatchData = async (itemCode) => {
	try {
		if (!itemCode) return [];

		const item = await db.items.get(itemCode);
		return item?.batch_no_data || [];
	} catch (error) {
		console.error("Error getting cached batch data:", error);
		return [];
	}
};

// Get cached serial number data for an item
export const getCachedSerialData = async (itemCode) => {
	try {
		if (!itemCode) return [];

		const item = await db.items.get(itemCode);
		return item?.serial_no_data || [];
	} catch (error) {
		console.error("Error getting cached serial data:", error);
		return [];
	}
};

function parseSerialNumbers(serialNumbers) {
	if (!serialNumbers) return [];
	return Array.isArray(serialNumbers)
		? serialNumbers
		: String(serialNumbers)
				.split("\n")
				.map((s) => s.trim())
				.filter(Boolean);
}

// Persist batch/serial data for a single cached item (partial updates supported)
export const persistItemBatchSerialData = async (itemCode, data) => {
	try {
		if (!itemCode || !data) return false;

		const update = {};
		if (data.batch_no_data !== undefined) update.batch_no_data = data.batch_no_data;
		if (data.serial_no_data !== undefined) update.serial_no_data = data.serial_no_data;

		if (Object.keys(update).length === 0) return false;

		const item = await db.items.get(itemCode);
		if (!item) {
			// Item not in cache yet — store batch/serial data so offline selection still works
			await db.items.put({ item_code: itemCode, ...update });
			return true;
		}

		await db.items.update(itemCode, update);
		return true;
	} catch (error) {
		console.error("Error persisting item batch/serial data:", error);
		return false;
	}
};

// Update batch/serial data for items in cache
export const updateItemBatchSerialData = async (batchSerialDataMap) => {
	try {
		if (!batchSerialDataMap || Object.keys(batchSerialDataMap).length === 0) return;

		// Update each item with its batch/serial data
		const updates = Object.entries(batchSerialDataMap).map(async ([itemCode, data]) => {
			await persistItemBatchSerialData(itemCode, {
				batch_no_data: data.batch_no_data || [],
				serial_no_data: data.serial_no_data || [],
			});
		});

		await Promise.all(updates);
		console.log(
			`Updated batch/serial data for ${Object.keys(batchSerialDataMap).length} items`
		);
		return true;
	} catch (error) {
		console.error("Error updating batch/serial data:", error);
		return false;
	}
};

// Remove consumed serial numbers from offline cache
export const consumeCachedSerials = async (itemCode, serialNumbers) => {
	try {
		if (!itemCode) return;

		const serials = await getCachedSerialData(itemCode);
		if (!serials.length) return;

		const toRemove = new Set(parseSerialNumbers(serialNumbers));
		const remaining = serials.filter((s) => !toRemove.has(s.serial_no));

		await persistItemBatchSerialData(itemCode, { serial_no_data: remaining });
	} catch (error) {
		console.error("Error consuming cached serials:", error);
	}
};

// Return serial numbers to offline cache (e.g. item removed from cart)
export const returnCachedSerials = async (itemCode, serialNumbers) => {
	try {
		if (!itemCode) return;

		const serials = await getCachedSerialData(itemCode);
		const toReturn = parseSerialNumbers(serialNumbers);
		if (!toReturn.length) return;

		const existing = new Set(serials.map((s) => s.serial_no));
		const warehouse = serials[0]?.warehouse;
		const added = toReturn
			.filter((serialNo) => !existing.has(serialNo))
			.map((serial_no) => ({ serial_no, warehouse }));

		if (!added.length) return;

		const merged = [...serials, ...added].sort((a, b) =>
			a.serial_no.localeCompare(b.serial_no, undefined, { numeric: true })
		);

		await persistItemBatchSerialData(itemCode, { serial_no_data: merged });
	} catch (error) {
		console.error("Error returning cached serials:", error);
	}
};

// Decrease batch quantity in offline cache after selection/sale
export const consumeCachedBatchQty = async (itemCode, batchNo, qty) => {
	try {
		if (!itemCode || !batchNo || !qty) return;

		const batches = await getCachedBatchData(itemCode);
		if (!batches.length) return;

		const updated = batches.map((batch) =>
			batch.batch_no === batchNo
				? { ...batch, batch_qty: Math.max(0, (batch.batch_qty || 0) - qty) }
				: batch
		);

		await persistItemBatchSerialData(itemCode, { batch_no_data: updated });
	} catch (error) {
		console.error("Error consuming cached batch qty:", error);
	}
};

// Get item with price
export const getItemWithPrice = async (itemCode, priceList) => {
	try {
		const item = await db.items.get(itemCode);
		if (!item) return null;

		if (priceList) {
			const price = await db.item_prices.get({
				price_list: priceList,
				item_code: itemCode,
			});
			if (price) {
				item.rate = price.rate;
				item.price_list_rate = price.rate;
			}
		}

		return item;
	} catch (error) {
		console.error("Error getting item with price:", error);
		return null;
	}
};

// Cache customers
export const cacheCustomers = async (customers) => {
	try {
		if (!customers || customers.length === 0) return;

		await db.customers.bulkPut(customers);
		await setSetting("customers_last_sync", Date.now());

		console.log(`Cached ${customers.length} customers`);
		return true;
	} catch (error) {
		console.error("Error caching customers:", error);
		return false;
	}
};

// Search cached customers
export const searchCachedCustomers = async (searchTerm, limit = 20) => {
	try {
		if (!searchTerm) {
			return limit > 0
				? await db.customers.limit(limit).toArray()
				: await db.customers.toArray();
		}

		const term = searchTerm.toLowerCase();

		const query = db.customers
			.where("customer_name")
			.startsWithIgnoreCase(term)
			.or("mobile_no")
			.startsWithIgnoreCase(term)
			.or("email_id")
			.startsWithIgnoreCase(term);

		const results = await (limit > 0 ? query.limit(limit).toArray() : query.toArray());

		return results;
	} catch (error) {
		console.error("Error searching cached customers:", error);
		return [];
	}
};

// Get items last sync time
export const getItemsLastSync = async () => {
	return await getSetting("items_last_sync", null);
};

// Get customers last sync time
export const getCustomersLastSync = async () => {
	return await getSetting("customers_last_sync", null);
};

// Check if cache is fresh (less than 24 hours old)
export const isCacheFresh = async (type = "items") => {
	const lastSync = type === "items" ? await getItemsLastSync() : await getCustomersLastSync();

	if (!lastSync) return false;

	const hoursSinceSync = (Date.now() - lastSync) / (1000 * 60 * 60);
	return hoursSinceSync < 24;
};

// Clear cache
export const clearItemsCache = async () => {
	try {
		await db.items.clear();
		await db.item_prices.clear();
		await setSetting("items_last_sync", null);
		console.log("Items cache cleared");
		return true;
	} catch (error) {
		console.error("Error clearing items cache:", error);
		return false;
	}
};

export const clearCustomersCache = async () => {
	try {
		await db.customers.clear();
		await setSetting("customers_last_sync", null);
		console.log("Customers cache cleared");
		return true;
	} catch (error) {
		console.error("Error clearing customers cache:", error);
		return false;
	}
};
