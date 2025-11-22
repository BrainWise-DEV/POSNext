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
				const searchable = `${item.item_code || ""} ${item.item_name || ""} ${item.description || ""}`.toLowerCase();

				// Word-order independent: all words must appear somewhere
				if (!searchWords.every(word => searchable.includes(word))) return null;

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

                const results = await (limit > 0
                        ? query.limit(limit).toArray()
                        : query.toArray());

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
