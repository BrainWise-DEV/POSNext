import { call } from "@/utils/apiWrapper";
import { logger } from "@/utils/logger";
import { CoalescingMutex } from "@/utils/mutex";
import { db, getSetting, setSetting } from "./db";
import { offlineState } from "./offlineState";
import { removeOfflineReceiptPayload } from "./offlineReceiptCache";
import { generateOfflineExpenseId, generateOfflineId } from "./uuid";

// Re-export for backwards compatibility
export { generateOfflineExpenseId, generateOfflineId };

// Create namespaced logger for sync operations
const log = logger.create("Sync");

// Mutex for sync operations
const syncMutex = new CoalescingMutex({ timeout: 60000, name: "InvoiceSync" });

// ============================================================================
// CONSTANTS
// ============================================================================

const SYNC_CONFIG = {
	MAX_RETRY_COUNT: 3,
	CLEANUP_AGE_DAYS: 7,
	PING_TIMEOUT_MS: 3000,
};

// Duplicate error patterns to detect already-synced invoices
const DUPLICATE_ERROR_PATTERNS = ["DUPLICATE_OFFLINE_INVOICE", "already been synced"];

// Temporary error patterns that should trigger a retry after delay
const SYNC_IN_PROGRESS_PATTERNS = ["SYNC_IN_PROGRESS", "currently being processed"];

// ============================================================================
// SERVER CONNECTIVITY
// ============================================================================

/**
 * Ping server to check connectivity
 * @returns {Promise<boolean>} Whether server is reachable
 */
export const pingServer = async () => {
	if (typeof window === "undefined") return true;

	try {
		const controller = new AbortController();
		const timeoutId = setTimeout(() => controller.abort(), SYNC_CONFIG.PING_TIMEOUT_MS);

		const response = await fetch("/api/method/pos_next.api.ping", {
			method: "GET",
			signal: controller.signal,
		});

		clearTimeout(timeoutId);
		const isOnline = response.ok;
		// Update centralized state (handles window sync automatically)
		offlineState.setServerOnline(isOnline);
		return isOnline;
	} catch (error) {
		// Server unreachable
		offlineState.setServerOnline(false);
		return false;
	}
};

/**
 * Check if currently offline
 * @returns {boolean}
 */
export const isOffline = () => {
	if (typeof window === "undefined") return false;
	return offlineState.isOffline;
};

// ============================================================================
// OFFLINE INVOICE QUEUE OPERATIONS
// ============================================================================

/**
 * Save invoice to offline queue with unique offline_id for deduplication
 * @param {Object} invoiceData - Invoice data to save
 * @returns {Promise<{success: boolean, id: number, offline_id: string}>}
 */
export const saveOfflineInvoice = async (invoiceData) => {
	if (!invoiceData.items?.length) {
		throw new Error("Cannot save empty invoice");
	}

	// Clean data (remove reactive properties) and add offline_id
	const cleanData = JSON.parse(JSON.stringify(invoiceData));
	const offlineId = generateOfflineId();
	cleanData.offline_id = offlineId;

	const id = await db.invoice_queue.add({
		offline_id: offlineId,
		data: cleanData,
		timestamp: Date.now(),
		synced: false,
		retry_count: 0,
	});

	await updateLocalStock(cleanData.items);

	log.info(`Invoice saved to offline queue`, { offline_id: offlineId });
	return { success: true, id, offline_id: offlineId };
};

/**
 * Get all pending (unsynced) offline invoices
 * @returns {Promise<Array>}
 */
export const getOfflineInvoices = async () => {
	try {
		return await db.invoice_queue.filter((inv) => !inv.synced && !inv.superseded).toArray();
	} catch (error) {
		log.error("Failed to get offline invoices", error);
		return [];
	}
};

/**
 * Look up a single queued offline invoice by its offline_id. Used to rebuild
 * a receipt payload after sessionStorage is wiped (e.g. a page refresh
 * between checkout and the auto-print).
 * @param {string} offlineId - pos_offline_<uuid>
 * @returns {Promise<Object|null>} The invoice data or null if not queued.
 */
export const getOfflineInvoiceByOfflineId = async (offlineId) => {
	if (!offlineId) return null;
	try {
		const row = await db.invoice_queue.where("offline_id").equals(offlineId).first();
		return row?.data || null;
	} catch (error) {
		log.error("Failed to look up offline invoice", { offlineId, error });
		return null;
	}
};

/**
 * Get count of pending offline invoices
 * @returns {Promise<number>}
 */
export const getOfflineInvoiceCount = async () => {
	try {
		return await db.invoice_queue.filter((inv) => !inv.synced && !inv.superseded).count();
	} catch (error) {
		log.error("Failed to get offline invoice count", error);
		return 0;
	}
};

/**
 * Delete an offline invoice by ID
 * @param {number} id - Invoice queue ID
 * @returns {Promise<boolean>}
 */
export const deleteOfflineInvoice = async (id) => {
	try {
		await db.invoice_queue.delete(id);
		return true;
	} catch (error) {
		log.error("Failed to delete offline invoice", { id, error });
		return false;
	}
};

// ============================================================================
// DEDUPLICATION CHECK
// ============================================================================

/**
 * Check if an offline_id has already been synced to the server.
 * @param {string} offlineId - The offline_id to check
 * @returns {Promise<{synced: boolean, sales_invoice?: string}>}
 */
export const checkOfflineIdSynced = async (offlineId) => {
	if (!offlineId) return { synced: false };

	try {
		const response = await call("pos_next.api.invoices.check_offline_invoice_synced", {
			offline_id: offlineId,
		});
		return response || { synced: false };
	} catch (error) {
		// If check fails, assume not synced - server will still deduplicate
		log.warn("Failed to check sync status", { offline_id: offlineId, error });
		return { synced: false };
	}
};

/**
 * Check if an error message indicates a duplicate invoice
 * @param {Error|string} error - Error to check
 * @returns {{isDuplicate: boolean, invoiceName: string|null}}
 */
const checkDuplicateError = (error) => {
	const errorMessage = error?.message || error?.exc || error?.title || String(error);
	const isDuplicate = DUPLICATE_ERROR_PATTERNS.some((pattern) => errorMessage.includes(pattern));

	if (!isDuplicate) return { isDuplicate: false, invoiceName: null };

	const match = errorMessage.match(/Sales Invoice: (\S+)/);
	return { isDuplicate: true, invoiceName: match?.[1] || null };
};

/**
 * Check if an error indicates another request is processing the same invoice
 * @param {Error|string} error - Error to check
 * @returns {boolean}
 */
const isSyncInProgressError = (error) => {
	const errorMessage = error?.message || error?.exc || error?.title || String(error);
	return SYNC_IN_PROGRESS_PATTERNS.some((pattern) => errorMessage.includes(pattern));
};

/**
 * Wait for a specified duration
 * @param {number} ms - Milliseconds to wait
 * @returns {Promise<void>}
 */
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// ============================================================================
// SYNC OPERATIONS
// ============================================================================

/**
 * Mark an invoice as synced in the local database and drop its cached
 * receipt payload — once the invoice exists on the server, print/detail
 * lookups should go through the normal server path.
 * @param {number} id - Invoice queue ID
 * @param {string} serverInvoice - Server invoice name
 * @param {string} [offlineId] - pos_offline_<uuid> cache key to evict
 */
const markInvoiceSynced = async (id, serverInvoice, offlineId) => {
	await db.invoice_queue.update(id, {
		synced: true,
		server_invoice: serverInvoice,
	});
	if (offlineId) removeOfflineReceiptPayload(offlineId);
};

/**
 * Increment retry count and optionally mark as failed
 * @param {Object} invoice - Invoice record
 * @param {string} errorMessage - Error message
 */
const handleSyncFailure = async (invoice, errorMessage) => {
	const newRetryCount = (invoice.retry_count || 0) + 1;
	const updates = { retry_count: newRetryCount };

	if (newRetryCount >= SYNC_CONFIG.MAX_RETRY_COUNT) {
		updates.sync_failed = true;
		updates.error = errorMessage;
	}

	await db.invoice_queue.update(invoice.id, updates);
};

/**
 * Convert pricing_rules to comma-separated string.
 * Returns empty string for invalid/malformed values.
 */
const stringifyPricingRules = (value) => {
	if (!value) return "";
	if (Array.isArray(value)) return value.filter(Boolean).join(",");
	if (typeof value !== "string") return "";

	const stripped = value.trim();
	if (!stripped.startsWith("[")) return stripped;

	try {
		const parsed = JSON.parse(stripped);
		if (Array.isArray(parsed)) return parsed.filter(Boolean).join(",");
	} catch (e) {
		log.warn("Invalid pricing_rules JSON, clearing value", { value: stripped.slice(0, 100) });
		return "";
	}
	return "";
};

/**
 * Normalize invoice data for server sync.
 * Items should already be formatted by formatItemsForSubmission() when saved.
 * This provides a safety net for legacy data.
 */
const normalizeInvoiceForSync = (invoiceData, offlineId) => ({
	...invoiceData,
	offline_id: offlineId || invoiceData.offline_id,
	items: invoiceData.items?.map((item) => ({
		...item,
		qty: item.qty || item.quantity || 1,
		pricing_rules: stringifyPricingRules(item.pricing_rules),
	})),
});

/**
 * Sync a single invoice to the server with retry for in-progress errors
 * @param {Object} invoice - Invoice queue record
 * @param {number} retryCount - Current retry attempt (for in-progress waits)
 * @returns {Promise<{status: 'success'|'skipped'|'failed', error?: Error}>}
 */
const syncInvoiceToServer = async (invoice, retryCount = 0) => {
	const MAX_IN_PROGRESS_RETRIES = 3;
	const IN_PROGRESS_WAIT_MS = 2000; // Wait 2 seconds between retries

	const offlineId = invoice.offline_id || invoice.data?.offline_id;

	// Pre-sync deduplication check
	if (offlineId) {
		const syncStatus = await checkOfflineIdSynced(offlineId);
		if (syncStatus.synced) {
			await markInvoiceSynced(invoice.id, syncStatus.sales_invoice, offlineId);
			log.debug("Invoice already synced, skipping", {
				id: invoice.id,
				offline_id: offlineId,
				sales_invoice: syncStatus.sales_invoice,
			});
			return { status: "skipped" };
		}
	}

	// Prepare and submit
	const invoiceData = normalizeInvoiceForSync(invoice.data, offlineId);

	try {
		const response = await call("pos_next.api.invoices.submit_invoice", {
			data: JSON.stringify({ invoice: invoiceData, data: {} }),
		});

		if (response.message || response.name) {
			const serverName = response.name || response.message;
			await markInvoiceSynced(invoice.id, serverName, offlineId);
			log.success("Invoice synced", {
				id: invoice.id,
				offline_id: offlineId,
				sales_invoice: serverName,
			});
			return { status: "success" };
		}

		throw new Error("Invalid server response");
	} catch (error) {
		// Handle "sync in progress" - another request is processing this invoice
		if (isSyncInProgressError(error) && retryCount < MAX_IN_PROGRESS_RETRIES) {
			log.debug("Invoice being processed by another request, waiting...", {
				id: invoice.id,
				retry: retryCount + 1,
			});
			await sleep(IN_PROGRESS_WAIT_MS);
			return syncInvoiceToServer(invoice, retryCount + 1);
		}

		// Re-throw other errors
		throw error;
	}
};

/**
 * Sync all pending offline invoices to server.
 * Uses a mutex to ensure only one sync operation runs at a time.
 * Concurrent callers will wait for the ongoing sync and receive its result.
 *
 * @returns {Promise<{success: number, failed: number, skipped: number, errors: Array}>}
 */
export const syncOfflineInvoices = async () => {
	if (isOffline()) {
		log.debug("Cannot sync while offline");
		return { success: 0, failed: 0, skipped: 0, errors: [] };
	}

	return await syncMutex.withLock(async () => {
		const pendingInvoices = await getOfflineInvoices();

		if (!pendingInvoices.length) {
			return { success: 0, failed: 0, skipped: 0, errors: [] };
		}

		log.info(`Starting sync of ${pendingInvoices.length} invoice(s)`);

		const result = { success: 0, failed: 0, skipped: 0, errors: [] };

		for (const invoice of pendingInvoices) {
			try {
				const syncResult = await syncInvoiceToServer(invoice);

				if (syncResult.status === "success") {
					result.success++;
				} else if (syncResult.status === "skipped") {
					result.skipped++;
				}
			} catch (error) {
				log.error("Failed to sync invoice", { id: invoice.id, error });

				// Check for duplicate error from server
				const { isDuplicate, invoiceName } = checkDuplicateError(error);
				if (isDuplicate) {
					await markInvoiceSynced(
						invoice.id,
						invoiceName,
						invoice.offline_id || invoice.data?.offline_id
					);
					log.debug("Invoice is duplicate, marked as synced", { id: invoice.id });
					result.skipped++;
					continue;
				}

				// Handle genuine failure
				result.errors.push({
					invoiceId: invoice.id,
					offlineId: invoice.offline_id,
					customer: invoice.data?.customer || "Walk-in Customer",
					error,
				});

				await handleSyncFailure(invoice, error.message);
				result.failed++;
			}
		}

		// Cleanup old synced invoices
		await cleanupSyncedInvoices();

		log.info("Sync completed", {
			success: result.success,
			skipped: result.skipped,
			failed: result.failed,
		});

		return result;
	}, log.debug.bind(log));
};

/**
 * Clean up synced invoices older than configured days
 */
const cleanupSyncedInvoices = async () => {
	const cutoff = Date.now() - SYNC_CONFIG.CLEANUP_AGE_DAYS * 24 * 60 * 60 * 1000;
	await db.invoice_queue.filter((inv) => inv.synced && inv.timestamp < cutoff).delete();
};

// ============================================================================
// LOCAL STOCK OPERATIONS
// ============================================================================

/**
 * Update local stock after invoice
 * @param {Array} items - Invoice items
 */
export const updateLocalStock = async (items) => {
	if (!items?.length) return;

	try {
		for (const item of items) {
			if (!item.item_code || !item.warehouse) continue;

			const currentStock = await db.stock.get({
				item_code: item.item_code,
				warehouse: item.warehouse,
			});

			const qty = item.quantity || item.qty || 0;
			const newQty = (currentStock?.qty || 0) - qty;

			await db.stock.put({
				item_code: item.item_code,
				warehouse: item.warehouse,
				qty: newQty,
				updated_at: Date.now(),
			});
		}
	} catch (error) {
		log.error("Failed to update local stock", error);
	}
};

/**
 * Get local stock for an item
 * @param {string} itemCode - Item code
 * @param {string} warehouse - Warehouse
 * @returns {Promise<number>}
 */
export const getLocalStock = async (itemCode, warehouse) => {
	try {
		const stock = await db.stock.get({ item_code: itemCode, warehouse });
		return stock?.qty || 0;
	} catch (error) {
		log.error("Failed to get local stock", { item_code: itemCode, warehouse, error });
		return 0;
	}
};

// ============================================================================
// OFFLINE PAYMENT OPERATIONS
// ============================================================================

/**
 * Save payment to offline queue
 * @param {Object} paymentData - Payment data
 * @returns {Promise<boolean>}
 */
export const saveOfflinePayment = async (paymentData) => {
	const cleanData = JSON.parse(JSON.stringify(paymentData));

	await db.payment_queue.add({
		data: cleanData,
		timestamp: Date.now(),
		synced: false,
		retry_count: 0,
	});

	log.info("Payment saved to offline queue");
	return true;
};

// ============================================================================
// INVOICE HISTORY CACHE OPERATIONS
// ============================================================================

/**
 * Cache invoice history for offline viewing
 * @param {Array} invoices - Array of invoice objects
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<boolean>}
 */
export const cacheInvoiceHistory = async (invoices, posProfile) => {
	if (!invoices || invoices.length === 0) return false;

	try {
		// Clean data and add pos_profile for filtering
		const invoicesToCache = invoices.map((invoice) => ({
			...JSON.parse(JSON.stringify(invoice)),
			pos_profile: posProfile,
			cached_at: Date.now(),
		}));

		await db.invoice_history.bulkPut(invoicesToCache);
		log.info(`Cached ${invoices.length} invoices for offline viewing`);
		return true;
	} catch (error) {
		log.error("Failed to cache invoice history", error);
		return false;
	}
};

/**
 * Get cached invoice history for offline viewing
 * @param {string} posProfile - POS Profile name (optional filter)
 * @param {Object} options - Query options
 * @param {number} options.limit - Max number of invoices to return
 * @param {string} options.customer - Filter by customer name
 * @param {string} options.fromDate - Filter by posting_date >= fromDate
 * @param {string} options.toDate - Filter by posting_date <= toDate
 * @returns {Promise<Array>}
 */
export const getCachedInvoiceHistory = async (posProfile, options = {}) => {
	try {
		const { limit = 100, customer, fromDate, toDate } = options;

		let query = db.invoice_history;

		// Filter by POS profile if provided
		if (posProfile) {
			query = query.where("pos_profile").equals(posProfile);
		}

		let invoices = await query.toArray();

		// Apply additional filters
		if (customer) {
			invoices = invoices.filter((inv) =>
				inv.customer?.toLowerCase().includes(customer.toLowerCase())
			);
		}

		if (fromDate) {
			invoices = invoices.filter((inv) => inv.posting_date >= fromDate);
		}

		if (toDate) {
			invoices = invoices.filter((inv) => inv.posting_date <= toDate);
		}

		// Sort by posting_date descending (newest first)
		invoices.sort((a, b) => {
			const dateA = new Date(b.posting_date + " " + (b.posting_time || "00:00:00"));
			const dateB = new Date(a.posting_date + " " + (a.posting_time || "00:00:00"));
			return dateA - dateB;
		});

		return invoices.slice(0, limit);
	} catch (error) {
		log.error("Failed to get cached invoice history", error);
		return [];
	}
};

/**
 * Clear cached invoice history
 * @param {string} posProfile - Optional POS Profile to clear (clears all if not provided)
 * @returns {Promise<boolean>}
 */
export const clearInvoiceHistoryCache = async (posProfile) => {
	try {
		if (posProfile) {
			await db.invoice_history.where("pos_profile").equals(posProfile).delete();
		} else {
			await db.invoice_history.clear();
		}
		log.info("Invoice history cache cleared");
		return true;
	} catch (error) {
		log.error("Failed to clear invoice history cache", error);
		return false;
	}
};

// ============================================================================
// UNPAID INVOICES CACHE OPERATIONS
// ============================================================================

/**
 * Cache unpaid invoices for offline viewing
 * @param {Array} invoices - Array of unpaid invoice objects
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<boolean>}
 */
export const cacheUnpaidInvoices = async (invoices, posProfile) => {
	if (!invoices || invoices.length === 0) {
		// Clear existing cache if no invoices
		try {
			await db.unpaid_invoices.where("pos_profile").equals(posProfile).delete();
		} catch (e) {
			// Ignore errors on clear
		}
		return true;
	}

	try {
		// Clean data and add pos_profile for filtering
		const invoicesToCache = invoices.map((invoice) => ({
			...JSON.parse(JSON.stringify(invoice)),
			pos_profile: posProfile,
			cached_at: Date.now(),
		}));

		// Clear existing cache for this profile first
		await db.unpaid_invoices.where("pos_profile").equals(posProfile).delete();

		// Add new data
		await db.unpaid_invoices.bulkPut(invoicesToCache);
		log.info(`Cached ${invoices.length} unpaid invoices for offline viewing`);
		return true;
	} catch (error) {
		log.error("Failed to cache unpaid invoices", error);
		return false;
	}
};

/**
 * Get cached unpaid invoices for offline viewing
 * @param {string} posProfile - POS Profile name
 * @param {Object} options - Query options
 * @param {number} options.limit - Max number of invoices to return
 * @returns {Promise<Array>}
 */
export const getCachedUnpaidInvoices = async (posProfile, options = {}) => {
	try {
		const { limit = 100 } = options;

		if (!posProfile) {
			return [];
		}

		let invoices = await db.unpaid_invoices.where("pos_profile").equals(posProfile).toArray();

		// Sort by outstanding_amount descending (highest first)
		invoices.sort((a, b) => {
			const amountA = parseFloat(b.outstanding_amount || 0);
			const amountB = parseFloat(a.outstanding_amount || 0);
			return amountA - amountB;
		});

		return invoices.slice(0, limit);
	} catch (error) {
		log.error("Failed to get cached unpaid invoices", error);
		return [];
	}
};

/**
 * Cache unpaid invoice summary for offline viewing
 * @param {Object} summary - Summary object with count, total_outstanding, total_paid
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<boolean>}
 */
export const cacheUnpaidSummary = async (summary, posProfile) => {
	try {
		await db.settings.put({
			key: `unpaid_summary_${posProfile}`,
			value: {
				...summary,
				cached_at: Date.now(),
			},
		});
		log.debug("Cached unpaid invoice summary");
		return true;
	} catch (error) {
		log.error("Failed to cache unpaid summary", error);
		return false;
	}
};

/**
 * Get cached unpaid invoice summary
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<Object>}
 */
export const getCachedUnpaidSummary = async (posProfile) => {
	try {
		const result = await db.settings.get(`unpaid_summary_${posProfile}`);
		return result?.value || { count: 0, total_outstanding: 0, total_paid: 0 };
	} catch (error) {
		log.error("Failed to get cached unpaid summary", error);
		return { count: 0, total_outstanding: 0, total_paid: 0 };
	}
};

// ============================================================================
// OFFLINE EXPENSE QUEUE
// ============================================================================

const EXPENSE_ALLOWED_EXTENSIONS = [
	".jpg",
	".jpeg",
	".png",
	".gif",
	".pdf",
	".txt",
	".csv",
	".doc",
	".docx",
	".xls",
	".xlsx",
	".odt",
	".ods",
];

const DEFAULT_EXPENSE_MAX_FILE_SIZE = 10 * 1024 * 1024;
const expenseSyncMutex = new CoalescingMutex({ timeout: 60000, name: "ExpenseSync" });

/**
 * Settings key for cached expense dialog bootstrap data (profile + shift).
 * Shift totals must not leak across opening shifts on the same profile.
 * @param {string} posProfile
 * @param {string} posOpeningShift
 * @returns {string}
 */
export const expenseDialogCacheKey = (posProfile, posOpeningShift) =>
	`expense_dialog_cache:${posProfile}:${posOpeningShift}`;

/**
 * Cache successful get_expense_dialog_data payload for offline open.
 * @param {string} posProfile
 * @param {string} posOpeningShift
 * @param {Object} payload
 */
export const cacheExpenseDialogData = async (posProfile, posOpeningShift, payload) => {
	if (!posProfile || !posOpeningShift || !payload) return false;
	try {
		const ok = await setSetting(expenseDialogCacheKey(posProfile, posOpeningShift), {
			...payload,
			pos_profile: posProfile,
			pos_opening_shift: posOpeningShift,
			cached_at: Date.now(),
		});
		return Boolean(ok);
	} catch (error) {
		log.error("Failed to cache expense dialog data", error);
		return false;
	}
};

/**
 * Bump cached shift expense total after a JE is created offline→online.
 * Keeps offline remaining allowance accurate without a full dialog reload.
 * @param {string} posProfile
 * @param {string} posOpeningShift
 * @param {number} amount
 * @returns {Promise<boolean>}
 */
export const bumpExpenseDialogCacheShiftTotal = async (posProfile, posOpeningShift, amount) => {
	const delta = Number(amount) || 0;
	if (!posProfile || !posOpeningShift || delta <= 0) return false;
	const cache = await getExpenseDialogCache(posProfile, posOpeningShift);
	if (!cache) return false;
	const shiftTotal = (Number(cache.shift_expense_total) || 0) + delta;
	const max = Number(cache.maximum_expense_amount) || 0;
	return cacheExpenseDialogData(posProfile, posOpeningShift, {
		...cache,
		shift_expense_total: shiftTotal,
		remaining_expense_amount: max > 0 ? Math.max(0, max - shiftTotal) : cache.remaining_expense_amount,
	});
};

/**
 * @param {string} posProfile
 * @param {string} posOpeningShift
 * @returns {Promise<Object|null>}
 */
export const getExpenseDialogCache = async (posProfile, posOpeningShift) => {
	if (!posProfile || !posOpeningShift) return null;
	try {
		const cache =
			(await getSetting(expenseDialogCacheKey(posProfile, posOpeningShift), null)) || null;
		if (!cache) return null;
		// Reject mismatched / legacy rows that somehow land in this key.
		if (cache.pos_opening_shift && cache.pos_opening_shift !== posOpeningShift) {
			return null;
		}
		if (cache.pos_profile && cache.pos_profile !== posProfile) {
			return null;
		}
		return cache;
	} catch (error) {
		log.error("Failed to read expense dialog cache", error);
		return null;
	}
};

/**
 * @param {string} fileName
 * @returns {boolean}
 */
const isAllowedExpenseExtension = (fileName) => {
	const lower = String(fileName || "").toLowerCase();
	const dot = lower.lastIndexOf(".");
	if (dot < 0) return false;
	return EXPENSE_ALLOWED_EXTENSIONS.includes(lower.slice(dot));
};

/**
 * Validate a queued attachment (File or {name,size,type,blob}).
 * @param {Object} fileLike
 * @param {number} maxFileSize
 * @returns {string|null} Error message or null
 */
export const validateExpenseQueueAttachment = (fileLike, maxFileSize = DEFAULT_EXPENSE_MAX_FILE_SIZE) => {
	const name = fileLike?.name || "";
	const size = Number(fileLike?.size ?? fileLike?.blob?.size ?? 0);
	if (!name || !isAllowedExpenseExtension(name)) {
		return `File type not allowed: ${name || "(unnamed)"}`;
	}
	if (!Number.isFinite(size) || size <= 0) {
		return `File is empty: ${name}`;
	}
	if (size > maxFileSize) {
		return `File exceeds max size: ${name}`;
	}
	return null;
};

/**
 * Remaining shift allowance using cached totals + pending local queue amounts.
 * @param {Object} options
 * @returns {number}
 */
export const getOfflineExpenseRemainingAllowance = ({
	maximumExpenseAmount = 0,
	shiftExpenseTotal = 0,
	pendingLocalTotal = 0,
} = {}) => {
	const max = Number(maximumExpenseAmount) || 0;
	if (max <= 0) return 0;
	return Math.max(0, max - (Number(shiftExpenseTotal) || 0) - (Number(pendingLocalTotal) || 0));
};

/**
 * Sum local expense amounts that are not yet reflected in cached shift_expense_total.
 * Rows marked cache_counted (JE created + cache bumped) are excluded to avoid double-subtract.
 * Unsynced rows without cache_counted — including JE-created-but-cache-stale — still count.
 * @param {string} posOpeningShift
 * @param {number} [excludeId]
 * @returns {Promise<number>}
 */
export const getPendingExpenseLocalTotal = async (posOpeningShift, excludeId = null) => {
	const pending = await getPendingExpenses();
	return pending.reduce((sum, row) => {
		if (excludeId != null && row.id === excludeId) return sum;
		if (row.data?.pos_opening_shift !== posOpeningShift) return sum;
		if (row.cache_counted) return sum;
		return sum + (Number(row.data?.amount) || 0);
	}, 0);
};

/**
 * Save expense + optional Blob attachments to IndexedDB queue.
 * @param {Object} expenseData
 * @param {Array<{name:string,type?:string,size?:number,blob:Blob}>} [attachments]
 * @param {Object} [limits] - { maximum_expense_amount, shift_expense_total, max_file_size }
 * @returns {Promise<{success:boolean,id:number,offline_id:string}>}
 */
export const saveOfflineExpense = async (expenseData, attachments = [], limits = {}) => {
	const amount = Number(expenseData?.amount);
	if (!Number.isFinite(amount) || amount <= 0) {
		throw new Error("Amount must be greater than zero");
	}
	if (!(expenseData?.remarks || "").trim()) {
		throw new Error("Remarks are required");
	}
	if (!expenseData?.expense_account || !expenseData?.mode_of_payment) {
		throw new Error("Expense account and mode of payment are required");
	}
	if (!expenseData?.pos_opening_shift || !expenseData?.pos_profile) {
		throw new Error("POS shift and profile are required");
	}

	const maxAmount = Number(limits.maximum_expense_amount);
	if (!Number.isFinite(maxAmount) || maxAmount <= 0) {
		throw new Error(
			"Maximum Expense Amount is not configured. Open expenses once while online to cache limits.",
		);
	}

	const pendingLocal = await getPendingExpenseLocalTotal(expenseData.pos_opening_shift);
	const remaining = getOfflineExpenseRemainingAllowance({
		maximumExpenseAmount: maxAmount,
		shiftExpenseTotal: Number(limits.shift_expense_total) || 0,
		pendingLocalTotal: pendingLocal,
	});
	if (amount > remaining) {
		throw new Error("Amount exceeds the remaining shift expense allowance");
	}

	const maxFileSize =
		Number(limits.max_file_size) > 0
			? Number(limits.max_file_size)
			: DEFAULT_EXPENSE_MAX_FILE_SIZE;

	const normalizedAttachments = [];
	for (const file of attachments || []) {
		const blob = file.blob || (file instanceof Blob ? file : null);
		const name = file.name || blob?.name || "";
		const size = file.size ?? blob?.size ?? 0;
		const type = file.type || blob?.type || "";
		const err = validateExpenseQueueAttachment({ name, size, type, blob }, maxFileSize);
		if (err) throw new Error(err);
		if (!blob) throw new Error(`Missing file data: ${name}`);
		normalizedAttachments.push({ name, type, size, blob });
	}

	const offlineId = generateOfflineExpenseId();
	const cleanData = {
		pos_opening_shift: expenseData.pos_opening_shift,
		pos_profile: expenseData.pos_profile,
		expense_account: expenseData.expense_account,
		amount,
		mode_of_payment: expenseData.mode_of_payment,
		employee: expenseData.employee || null,
		remarks: String(expenseData.remarks).trim(),
		company_currency: expenseData.company_currency || null,
		offline_id: offlineId,
	};

	const id = await db.expense_queue.add({
		offline_id: offlineId,
		data: cleanData,
		attachments: normalizedAttachments,
		timestamp: Date.now(),
		synced: false,
		retry_count: 0,
	});

	log.info("Expense saved to offline queue", { offline_id: offlineId, attachments: normalizedAttachments.length });
	return { success: true, id, offline_id: offlineId };
};

/**
 * @returns {Promise<Array>}
 */
export const getPendingExpenses = async () => {
	try {
		return await db.expense_queue.filter((row) => !row.synced).toArray();
	} catch (error) {
		log.error("Failed to get pending expenses", error);
		return [];
	}
};

/**
 * @returns {Promise<number>}
 */
export const getPendingExpenseCount = async () => {
	try {
		return await db.expense_queue.filter((row) => !row.synced).count();
	} catch (error) {
		log.error("Failed to get pending expense count", error);
		return 0;
	}
};

/**
 * Delete an unsynced expense queue row (local only).
 * Refused once a server Journal Entry exists — cash already posted.
 * @param {number} id
 * @returns {Promise<boolean>}
 */
export const deleteOfflineExpense = async (id) => {
	try {
		const row = await db.expense_queue.get(id);
		if (!row) return false;
		if (row.synced) {
			throw new Error("Cannot delete a synced expense");
		}
		if (row.server_journal_entry) {
			throw new Error(
				"Journal Entry already created on the server. Discard remaining attachments instead of deleting.",
			);
		}
		await db.expense_queue.delete(id);
		return true;
	} catch (error) {
		log.error("Failed to delete offline expense", { id, error });
		throw error;
	}
};

/**
 * @param {string} offlineId
 * @returns {Promise<{synced:boolean,journal_entry?:string}>}
 */
export const checkOfflineExpenseSynced = async (offlineId) => {
	if (!offlineId) return { synced: false };
	try {
		const response = await call("pos_next.api.expenses.check_offline_expense_synced", {
			offline_id: offlineId,
		});
		return response || { synced: false };
	} catch (error) {
		log.warn("Failed to check offline expense sync status", { offlineId, error });
		return { synced: false };
	}
};

const markExpenseSynced = async (id, journalEntry, offlineId) => {
	await db.expense_queue.update(id, {
		synced: true,
		server_journal_entry: journalEntry,
		attachments: [],
		sync_failed: false,
		error: null,
		cache_counted: true,
		synced_at: Date.now(),
	});
	log.debug("Marked expense synced", { id, offline_id: offlineId, journal_entry: journalEntry });
};

/**
 * Drop remaining queued attachments after JE exists (keep JE; clear local retry queue).
 * @param {number} id
 * @returns {Promise<boolean>}
 */
export const discardOfflineExpenseAttachments = async (id) => {
	const row = await db.expense_queue.get(id);
	if (!row) return false;
	if (!row.server_journal_entry) {
		throw new Error("No server Journal Entry yet — delete the pending expense instead");
	}
	await markExpenseSynced(id, row.server_journal_entry, row.offline_id);
	return true;
};

const rememberExpenseJournalEntry = async (expense, journalEntry) => {
	const amount = Number(expense.data?.amount) || 0;
	const posProfile = expense.data?.pos_profile;
	const posOpeningShift = expense.data?.pos_opening_shift;
	let cacheCounted = Boolean(expense.cache_counted);
	if (!cacheCounted && posProfile && posOpeningShift && amount > 0) {
		cacheCounted = await bumpExpenseDialogCacheShiftTotal(
			posProfile,
			posOpeningShift,
			amount,
		);
	}
	await db.expense_queue.update(expense.id, {
		server_journal_entry: journalEntry,
		error: null,
		cache_counted: cacheCounted,
	});
};

const isExpenseDuplicateError = (error) => {
	const message = error?.message || error?.exc || error?.title || String(error);
	return (
		Boolean(error?.duplicate_prevented) ||
		message.includes("duplicate_prevented") ||
		message.includes("already recorded") ||
		message.includes("already been synced")
	);
};

const uploadExpenseAttachmentBlob = async ({ blob, name, journalEntry, posOpeningShift, posProfile }) => {
	const formData = new FormData();
	formData.append("file", blob, name);
	formData.append("journal_entry", journalEntry);
	formData.append("pos_opening_shift", posOpeningShift);
	formData.append("pos_profile", posProfile);

	const response = await fetch("/api/method/pos_next.api.expenses.attach_pos_expense_file", {
		method: "POST",
		headers: {
			"X-Frappe-CSRF-Token": window.csrf_token,
		},
		body: formData,
	});
	const responseData = await response.json().catch(() => ({}));
	if (!response.ok || responseData.exc) {
		const message =
			responseData?.message ||
			responseData?._error_message ||
			`Failed to attach ${name}`;
		throw new Error(typeof message === "string" ? message : `Failed to attach ${name}`);
	}
	if (!responseData.message?.file_url && !responseData.message?.name) {
		throw new Error(`Attach did not return a file for ${name}`);
	}
	return responseData.message;
};

const isExpenseSyncInProgressError = (error) => {
	const message = error?.message || error?.exc || error?.title || String(error);
	return message.includes("SYNC_IN_PROGRESS") || message.includes("currently being processed");
};

/**
 * Sync one expense queue row: create JE (deduped) then upload remaining blobs.
 * @param {Object} expense
 * @param {number} [retryCount]
 */
const syncExpenseToServer = async (expense, retryCount = 0) => {
	const MAX_IN_PROGRESS_RETRIES = 3;
	const IN_PROGRESS_WAIT_MS = 2000;
	const offlineId = expense.offline_id || expense.data?.offline_id;
	let journalEntry = expense.server_journal_entry || null;

	if ((expense.retry_count || 0) >= SYNC_CONFIG.MAX_RETRY_COUNT && !journalEntry) {
		throw new Error(expense.error || "Expense sync retry limit exceeded");
	}

	if (!journalEntry && offlineId) {
		const syncStatus = await checkOfflineExpenseSynced(offlineId);
		if (syncStatus.synced && syncStatus.journal_entry) {
			journalEntry = syncStatus.journal_entry;
			await rememberExpenseJournalEntry(expense, journalEntry);
			expense = { ...expense, server_journal_entry: journalEntry, cache_counted: true };
		}
	}

	if (!journalEntry) {
		try {
			const response = await call("pos_next.api.expenses.create_pos_expense", {
				pos_opening_shift: expense.data.pos_opening_shift,
				pos_profile: expense.data.pos_profile,
				expense_account: expense.data.expense_account,
				amount: expense.data.amount,
				mode_of_payment: expense.data.mode_of_payment,
				employee: expense.data.employee || null,
				remarks: expense.data.remarks,
				offline_id: offlineId,
			});
			journalEntry = response?.journal_entry || response?.name;
			if (!journalEntry) {
				throw new Error("Invalid create_pos_expense response");
			}
			await rememberExpenseJournalEntry(expense, journalEntry);
			expense = { ...expense, server_journal_entry: journalEntry, cache_counted: true };
		} catch (error) {
			if (isExpenseSyncInProgressError(error) && retryCount < MAX_IN_PROGRESS_RETRIES) {
				await new Promise((r) => setTimeout(r, IN_PROGRESS_WAIT_MS));
				return syncExpenseToServer(expense, retryCount + 1);
			}

			if (isExpenseDuplicateError(error) && offlineId) {
				const syncStatus = await checkOfflineExpenseSynced(offlineId);
				if (syncStatus.synced && syncStatus.journal_entry) {
					journalEntry = syncStatus.journal_entry;
					await rememberExpenseJournalEntry(expense, journalEntry);
					expense = { ...expense, server_journal_entry: journalEntry };
				} else {
					throw error;
				}
			} else {
				throw error;
			}
		}
	} else if (!expense.cache_counted) {
		await rememberExpenseJournalEntry(expense, journalEntry);
	}

	const attachments = Array.isArray(expense.attachments) ? [...expense.attachments] : [];
	for (let index = 0; index < attachments.length; index++) {
		const att = attachments[index];
		try {
			await uploadExpenseAttachmentBlob({
				blob: att.blob,
				name: att.name,
				journalEntry,
				posOpeningShift: expense.data.pos_opening_shift,
				posProfile: expense.data.pos_profile,
			});
		} catch (error) {
			const remaining = attachments.slice(index);
			await rememberExpenseJournalEntry(
				{ ...expense, server_journal_entry: journalEntry },
				journalEntry,
			);
			await db.expense_queue.update(expense.id, {
				attachments: remaining,
				synced: false,
				sync_failed: true,
				error: error.message || String(error),
				retry_count: (expense.retry_count || 0) + 1,
			});
			throw error;
		}
	}

	await markExpenseSynced(expense.id, journalEntry, offlineId);
	return { status: "success", journal_entry: journalEntry };
};

/**
 * Sync all pending offline expenses.
 * @returns {Promise<{success:number,failed:number,skipped:number,errors:Array}>}
 */
export const syncOfflineExpenses = async () => {
	if (isOffline()) {
		log.debug("Cannot sync expenses while offline");
		return { success: 0, failed: 0, skipped: 0, errors: [] };
	}

	return await expenseSyncMutex.withLock(async () => {
		const pending = await getPendingExpenses();
		if (!pending.length) {
			return { success: 0, failed: 0, skipped: 0, errors: [] };
		}

		log.info(`Starting sync of ${pending.length} expense(s)`);
		const result = { success: 0, failed: 0, skipped: 0, errors: [] };

		for (const expense of pending) {
			try {
				// Re-read row in case prior attach-only update changed attachments
				const fresh = (await db.expense_queue.get(expense.id)) || expense;
				if (fresh.synced) {
					result.skipped++;
					continue;
				}
				const syncResult = await syncExpenseToServer(fresh);
				if (syncResult.status === "success") {
					result.success++;
				} else {
					result.skipped++;
				}
			} catch (error) {
				log.error("Failed to sync expense", { id: expense.id, error });
				result.errors.push({
					expenseId: expense.id,
					offlineId: expense.offline_id,
					error,
				});
				await db.expense_queue.update(expense.id, {
					sync_failed: true,
					error: error.message || String(error),
					retry_count: (expense.retry_count || 0) + 1,
				});
				result.failed++;
			}
		}

		const cutoff = Date.now() - SYNC_CONFIG.CLEANUP_AGE_DAYS * 24 * 60 * 60 * 1000;
		await db.expense_queue.filter((row) => row.synced && row.timestamp < cutoff).delete();

		log.info("Expense sync completed", {
			success: result.success,
			skipped: result.skipped,
			failed: result.failed,
		});
		return result;
	}, log.debug.bind(log));
};
