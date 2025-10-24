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

// Search cached items with fuzzy word-order independent matching
export const searchCachedItems = async (searchTerm, limit = 50) => {
	try {
		if (!searchTerm) {
			return await db.items.limit(limit).toArray();
		}

		const term = searchTerm.toLowerCase();
		const searchWords = term.split(/\s+/).filter((word) => word.length > 0);

		// Single word search - use optimized index queries
		if (searchWords.length === 1) {
			const results = await db.items
				.where("item_code")
				.startsWithIgnoreCase(term)
				.or("item_name")
				.startsWithIgnoreCase(term)
				.or("barcodes")
				.equals(term)
				.limit(limit)
				.toArray();

			return results;
		}

		// Multi-word fuzzy search - fetch items and filter in JavaScript
		// Get a larger set for better multi-word matching
		const allItems = await db.items.limit(limit * 5).toArray();

		// Filter items where ALL search words appear (order independent)
		const results = allItems.filter((item) => {
			const searchableText = `${item.item_code || ""} ${item.item_name || ""} ${
				item.description || ""
			} ${item.barcodes?.join(" ") || ""}`.toLowerCase();

			// Check if all words are present in any order
			return searchWords.every((word) => searchableText.includes(word));
		});

		return results.slice(0, limit);
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
			return await db.customers.limit(limit).toArray();
		}

		const term = searchTerm.toLowerCase();

		const results = await db.customers
			.where("customer_name")
			.startsWithIgnoreCase(term)
			.or("mobile_no")
			.startsWithIgnoreCase(term)
			.or("email_id")
			.startsWithIgnoreCase(term)
			.limit(limit)
			.toArray();

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
