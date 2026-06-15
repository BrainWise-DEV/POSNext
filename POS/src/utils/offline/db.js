import Dexie from "dexie";
import { logger } from "../logger";

/** @type {import('../logger').Logger} */
const log = logger.create("OfflineDB");

/**
 * @fileoverview IndexedDB persistence layer for POS Next offline functionality.
 *
 * This module provides:
 * - Auto-versioned Dexie database with schema migration
 * - Offline caching for items, customers, stock, prices
 * - Queue management for offline invoices and payments
 * - Settings persistence and translation cache
 *
 * Schema changes are auto-detected via hash comparison and trigger version bumps.
 *
 * @module db
 * @see {@link https://dexie.org/} Dexie.js documentation
 */

/** @type {Dexie} Main database instance */
export const db = new Dexie("pos_next_offline");

/**
 * Database schema definition.
 * Modify this object to change the schema - version will auto-increment.
 *
 * Index notation:
 * - `&` = unique primary key
 * - `++` = auto-increment primary key
 * - `*` = multi-entry index (array field)
 * - `[a+b]` = compound index
 *
 * @constant {Object}
 */
const CURRENT_SCHEMA = {
	// Key-value store for settings and metadata
	settings: "&key",

	// Invoice queue for offline submissions
	// offline_id is a unique UUID for deduplication across syncs
	invoice_queue: "++id, &offline_id, timestamp, synced",

	// Items cache with searchable fields
	// variant_of index allows querying variants by their template item
	// brand index allows efficient brand-based filtering in offline mode
	items: "&item_code, item_name, item_group, variant_of, has_variants, brand, *barcodes",

	// Customers cache
	customers: "&name, customer_name, mobile_no, email_id",

	// Price list cache
	item_prices: "&[price_list+item_code], price_list, item_code",

	// Local stock cache
	stock: "&[item_code+warehouse], item_code, warehouse",

	// Payment methods cache
	payment_methods: "&mode_of_payment, pos_profile",

	// Sales persons cache
	sales_persons: "&name, pos_profile",

	// Payment queue for offline payments
	payment_queue: "++id, timestamp, synced",

	// Drafts (already handled by draftManager, but keeping for consistency)
	drafts: "++id, draft_id, timestamp",

	// Translations cache for offline language support
	translations: "&locale, timestamp",

	// Promotional offers cache for offline use
	// Indexed by name (unique), filterable by pos_profile
	offers: "&name, pos_profile, apply_on, valid_upto",

	// Invoice history cache for offline viewing
	// Stores submitted invoices for offline access
	invoice_history: "&name, pos_profile, posting_date, customer",

	// Unpaid invoices cache for offline viewing
	// Stores invoices with outstanding amounts for partial payment management
	unpaid_invoices: "&name, pos_profile, outstanding_amount, customer",

	// One-time-per-customer offer redemptions cache. Keyed by customer.
	// Row shape: { customer, serverRules: string[], offlineRules: { [invoiceId]: string[] } }
	//   serverRules  — authoritative set from the server (replaced wholesale on
	//                  each online fetch, so a server-side release self-heals).
	//   offlineRules — redemptions from not-yet-synced offline sales, keyed by
	//                  invoice id so a voided offline sale can release just its own.
	// The effective redeemed set (what the offline gate checks) is the union of
	// serverRules and every offlineRules entry. Legacy rows store a flat `rules`
	// array; the helpers read it for backward compatibility.
	one_time_redemptions: "&customer",
};

/**
 * Generates a 32-bit hash of the schema for change detection.
 * Uses djb2 algorithm for fast, deterministic hashing.
 * @param {Object} schema - Schema object to hash
 * @returns {number} Positive 32-bit integer hash
 * @private
 */
function getSchemaHash(schema) {
	const schemaString = JSON.stringify(schema);
	let hash = 0;
	for (let i = 0; i < schemaString.length; i++) {
		const char = schemaString.charCodeAt(i);
		hash = (hash << 5) - hash + char;
		hash = hash & hash; // Convert to 32-bit integer
	}
	return Math.abs(hash);
}

/**
 * Determines the current schema version using localStorage tracking.
 * Compares stored hash against current schema hash to detect changes.
 * Auto-increments version when schema changes are detected.
 *
 * @returns {number} Current schema version number
 * @private
 */
function getSchemaVersion() {
	const schemaHash = getSchemaHash(CURRENT_SCHEMA);
	const storedHash = localStorage.getItem("pos_next_schema_hash");
	const storedVersion = Number.parseInt(localStorage.getItem("pos_next_schema_version") || "1");

	if (storedHash !== schemaHash.toString()) {
		// Schema changed, increment version
		const newVersion = storedVersion + 1;
		log.info(`Schema changed detected. Upgrading from v${storedVersion} to v${newVersion}`);
		localStorage.setItem("pos_next_schema_hash", schemaHash.toString());
		localStorage.setItem("pos_next_schema_version", newVersion.toString());
		return newVersion;
	}

	return storedVersion;
}

// Apply schema with auto-versioning
const schemaVersion = getSchemaVersion();
log.debug(`Initializing database with schema version: ${schemaVersion}`);
db.version(schemaVersion).stores(CURRENT_SCHEMA);

/**
 * Opens the database connection.
 * Called automatically on module import.
 * @returns {Promise<boolean>} True if opened successfully
 */
export const initDB = async () => {
	try {
		await db.open();
		log.success("POS Next offline database initialized");
		return true;
	} catch (error) {
		log.error("Failed to initialize offline database:", error);
		return false;
	}
};

/**
 * Verifies database health and attempts recovery if needed.
 * Handles VersionError and InvalidStateError by recreating the database.
 * @returns {Promise<boolean>} True if database is healthy or recovered
 */
export const checkDBHealth = async () => {
	try {
		await db.settings.get("health_check");
		return true;
	} catch (error) {
		log.error("Database health check failed:", error);

		// Try to reopen
		try {
			if (db.isOpen()) {
				db.close();
			}
			await db.open();
			log.info("Database reopened successfully");
			return true;
		} catch (reopenError) {
			log.error("Failed to reopen database:", reopenError);

			// If corrupted, recreate
			if (reopenError.name === "VersionError" || reopenError.name === "InvalidStateError") {
				log.warn("Database appears corrupted, recreating...");
				try {
					await Dexie.delete("pos_next_offline");
					await db.open();
					log.success("Database recreated successfully");
					return true;
				} catch (recreateError) {
					log.error("Failed to recreate database:", recreateError);
					return false;
				}
			}
			return false;
		}
	}
};

/**
 * Retrieves a setting value from the database.
 * @param {string} key - Setting key to retrieve
 * @param {*} [defaultValue=null] - Value to return if key not found
 * @returns {Promise<*>} Stored value or defaultValue
 */
export const getSetting = async (key, defaultValue = null) => {
	try {
		const result = await db.settings.get(key);
		return result ? result.value : defaultValue;
	} catch (error) {
		log.error(`Error getting setting ${key}:`, error);
		return defaultValue;
	}
};

/**
 * Stores a setting value in the database.
 * @param {string} key - Setting key
 * @param {*} value - Value to store (must be IndexedDB-serializable)
 * @returns {Promise<void>}
 */
export const setSetting = async (key, value) => {
	try {
		await db.settings.put({ key, value });
	} catch (error) {
		log.error(`Error setting ${key}:`, error);
	}
};

/**
 * Normalize a cached row (or undefined) into { serverRules, offlineRules }.
 * Legacy rows stored a flat `rules` array; treat those as serverRules.
 */
const _normalizeRedemptionRow = (row) => {
	if (!row) return { serverRules: [], offlineRules: {} };
	const offlineRules = row.offlineRules && typeof row.offlineRules === "object" ? row.offlineRules : {};
	let serverRules = Array.isArray(row.serverRules) ? row.serverRules : [];
	// Backward compat: fold a legacy flat `rules` array into serverRules.
	if (Array.isArray(row.rules)) {
		serverRules = Array.from(new Set([...serverRules, ...row.rules]));
	}
	return { serverRules, offlineRules };
};

/** The effective redeemed set = serverRules ∪ all offlineRules entries. */
const _effectiveRedeemed = ({ serverRules, offlineRules }) => {
	const all = new Set(serverRules);
	for (const rules of Object.values(offlineRules)) {
		for (const rule of rules || []) all.add(rule);
	}
	return Array.from(all);
};

/**
 * Get the effective cached one-time redeemed Pricing Rule names for a customer
 * (server redemptions plus not-yet-synced offline redemptions).
 * @param {string} customer - Customer name
 * @returns {Promise<string[]>} Redeemed rule names (empty array if none/unknown)
 */
export const getOneTimeRedemptions = async (customer) => {
	if (!customer) return [];
	try {
		const row = await db.one_time_redemptions.get(customer);
		return _effectiveRedeemed(_normalizeRedemptionRow(row));
	} catch (error) {
		log.error(`Error reading one-time redemptions for ${customer}:`, error);
		return [];
	}
};

/**
 * Read a customer's redemption row, apply `mutate` to the normalized
 * { serverRules, offlineRules }, persist it, and return the effective set.
 * The shared read-mutate-write path for every redemption writer below.
 */
const _putRedemptionRow = async (customer, mutate) => {
	const row = _normalizeRedemptionRow(await db.one_time_redemptions.get(customer));
	mutate(row);
	await db.one_time_redemptions.put({
		customer,
		serverRules: row.serverRules,
		offlineRules: row.offlineRules,
	});
	return _effectiveRedeemed(row);
};

/**
 * Replace the authoritative SERVER redemption set for a customer (used after an
 * online fetch). Preserves not-yet-synced offline redemptions, so a server-side
 * release self-heals on reconnect without losing offline-only redemptions.
 * @param {string} customer - Customer name
 * @param {string[]} serverRules - Redeemed Pricing Rule names from the server
 * @returns {Promise<string[]>} The effective redeemed set after the update
 */
export const setOneTimeRedemptions = async (customer, serverRules = []) => {
	if (!customer) return [];
	try {
		return await _putRedemptionRow(customer, (row) => {
			row.serverRules = Array.from(new Set(serverRules));
		});
	} catch (error) {
		log.error(`Error saving one-time redemptions for ${customer}:`, error);
		return await getOneTimeRedemptions(customer);
	}
};

/**
 * Record redemptions made during an OFFLINE checkout, keyed by invoice id so a
 * later void of that invoice can release exactly its own redemptions.
 * @param {string} customer - Customer name
 * @param {string[]} rules - Newly redeemed Pricing Rule names
 * @param {string} invoiceId - Offline invoice id these redemptions belong to
 * @returns {Promise<string[]>} The effective redeemed set after the update
 */
export const addOfflineRedemptions = async (customer, rules = [], invoiceId = "_") => {
	if (!customer || !rules.length) return await getOneTimeRedemptions(customer);
	try {
		return await _putRedemptionRow(customer, (row) => {
			const existing = row.offlineRules[invoiceId] || [];
			row.offlineRules[invoiceId] = Array.from(new Set([...existing, ...rules]));
		});
	} catch (error) {
		log.error(`Error appending offline redemptions for ${customer}:`, error);
		return await getOneTimeRedemptions(customer);
	}
};

/**
 * Release the offline redemptions recorded for a specific invoice (used when an
 * offline sale is voided/deleted/superseded before it ever reached the server).
 * Server redemptions are untouched. If `customer` is unknown, scans all rows.
 * @param {string} invoiceId - Offline invoice id whose redemptions to release
 * @param {string} [customer] - Customer name, if known (faster keyed lookup)
 * @returns {Promise<string[]>} The affected customer's effective set, or [] for a scan
 */
export const releaseOfflineRedemptions = async (invoiceId, customer = null) => {
	if (!invoiceId) return [];
	try {
		if (customer) {
			return await _putRedemptionRow(customer, (row) => {
				delete row.offlineRules[invoiceId];
			});
		}
		// Unknown customer: scan all rows and drop this invoice's bucket wherever found.
		for (const raw of await db.one_time_redemptions.toArray()) {
			if (raw?.offlineRules && invoiceId in raw.offlineRules) {
				await _putRedemptionRow(raw.customer, (row) => {
					delete row.offlineRules[invoiceId];
				});
			}
		}
		return [];
	} catch (error) {
		log.error(`Error releasing offline redemptions for invoice ${invoiceId}:`, error);
		return [];
	}
};

/**
 * Clear all cached data (items, customers, stock, etc.)
 * Preserves critical data like invoices, drafts, and settings
 * @param {Object} options - Options for clearing
 * @param {boolean} options.preserveInvoices - Keep invoice queue (default: true)
 * @param {boolean} options.preserveDrafts - Keep drafts (default: true)
 * @param {boolean} options.preserveSettings - Keep settings (default: true)
 * @returns {Promise<Object>} - Status of cleared tables
 */
export const clearCachedData = async (options = {}) => {
	const { preserveInvoices = true, preserveDrafts = true, preserveSettings = true } = options;

	const results = {
		items: 0,
		customers: 0,
		stock: 0,
		item_prices: 0,
		payment_methods: 0,
		sales_persons: 0,
		invoices: 0,
		payments: 0,
		drafts: 0,
		settings: 0,
	};

	try {
		// Always clear these cache tables
		results.items = await db.items.clear();
		results.customers = await db.customers.clear();
		results.stock = await db.stock.clear();
		results.item_prices = await db.item_prices.clear();
		results.payment_methods = await db.payment_methods.clear();
		results.sales_persons = await db.sales_persons.clear();

		// Conditionally clear invoice and payment queues
		if (!preserveInvoices) {
			results.invoices = await db.invoice_queue.clear();
			results.payments = await db.payment_queue.clear();
		}

		// Conditionally clear drafts
		if (!preserveDrafts) {
			results.drafts = await db.drafts.clear();
		}

		// Conditionally clear settings
		if (!preserveSettings) {
			results.settings = await db.settings.clear();
		}

		log.info("Cached data cleared:", results);
		return { success: true, cleared: results };
	} catch (error) {
		log.error("Error clearing cached data:", error);
		return { success: false, error: error.message, cleared: results };
	}
};

/**
 * NUCLEAR OPTION: Delete entire database and recreate
 * Use with caution - clears EVERYTHING including invoices and drafts
 * @returns {Promise<boolean>} - Success status
 */
export const nukeDatabase = async () => {
	try {
		log.warn("NUKING DATABASE - All data will be lost!");

		// Close database connection
		if (db.isOpen()) {
			db.close();
		}

		// Delete entire database
		await Dexie.delete("pos_next_offline");

		// Clear localStorage schema tracking
		localStorage.removeItem("pos_next_schema_hash");
		localStorage.removeItem("pos_next_schema_version");

		// Recreate database
		await db.open();

		log.success("Database nuked and recreated successfully");
		return true;
	} catch (error) {
		log.error("Error nuking database:", error);
		return false;
	}
};

/**
 * Clear browser cache and localStorage (POS-specific data only)
 * @returns {Object} - Status of cleared data
 */
export const clearBrowserCache = () => {
	const results = {
		localStorage: 0,
		sessionStorage: 0,
	};

	try {
		// Clear POS-specific localStorage items
		const keysToRemove = [];
		for (let i = 0; i < localStorage.length; i++) {
			const key = localStorage.key(i);
			if (key?.startsWith("pos_next_") || key?.startsWith("frappe_")) {
				keysToRemove.push(key);
			}
		}

		keysToRemove.forEach((key) => {
			localStorage.removeItem(key);
			results.localStorage++;
		});

		// Clear sessionStorage
		const sessionKeys = [];
		for (let i = 0; i < sessionStorage.length; i++) {
			const key = sessionStorage.key(i);
			if (key?.startsWith("pos_next_") || key?.startsWith("frappe_")) {
				sessionKeys.push(key);
			}
		}

		sessionKeys.forEach((key) => {
			sessionStorage.removeItem(key);
			results.sessionStorage++;
		});

		log.info("Browser cache cleared:", results);
		return { success: true, cleared: results };
	} catch (error) {
		log.error("Error clearing browser cache:", error);
		return { success: false, error: error.message, cleared: results };
	}
};

// Initialize database on import
initDB();
