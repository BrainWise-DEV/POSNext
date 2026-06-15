/**
 * POS Sync Store
 *
 * Manages offline synchronization state and operations for the POS system.
 * Handles invoice caching, sync operations, and offline state management.
 *
 * Key Design Decision:
 * This store subscribes directly to offlineState instead of using the useOffline()
 * composable. This is intentional because Pinia stores are singletons that persist
 * across component remounts (e.g., when changing language). Using Vue lifecycle
 * hooks (onMounted/onUnmounted) from composables would cause the subscription to
 * break when components remount.
 *
 * @module stores/posSync
 */

import { useToast } from "@/composables/useToast";
import {
	cacheCustomersFromServer,
	cachePaymentMethodsFromServer,
	cacheSalesPersonsFromServer,
	syncOfflineInvoices,
	cacheInvoiceHistory,
	cacheUnpaidInvoices,
	cacheUnpaidSummary,
} from "@/utils/offline";
import { call } from "@/utils/apiWrapper";
import { releaseOfflineRedemptions } from "@/utils/offline/db";
import { logger } from "@/utils/logger";
import { offlineState } from "@/utils/offline/offlineState";
import { offlineWorker } from "@/utils/offline/workerClient";
import { defineStore } from "pinia";
import { computed, ref } from "vue";

const log = logger.create("POSSync");

export const usePOSSyncStore = defineStore("posSync", () => {
	// =========================================================================
	// STATE
	// =========================================================================

	/** Current offline status - synced with offlineState singleton */
	const isOffline = ref(offlineState.isOffline);

	/** Number of invoices pending sync */
	const pendingInvoicesCount = ref(0);

	/** Whether a sync operation is in progress */
	const isSyncing = ref(false);

	/** Current connection quality metrics */
	const connectionQuality = ref(offlineState.getConnectionQuality());

	/** List of pending invoices for display */
	const pendingInvoicesList = ref([]);

	/** Track previous offline state for detecting online/offline transitions */
	let wasOffline = offlineState.isOffline;

	// =========================================================================
	// TOAST NOTIFICATIONS
	// =========================================================================

	const { showSuccess, showError, showWarning } = useToast();

	// =========================================================================
	// OFFLINE STATE SUBSCRIPTION
	// =========================================================================

	/**
	 * Subscribe to offlineState changes at the store level.
	 * This subscription persists for the app's lifetime since Pinia stores are singletons.
	 */
	offlineState.subscribe(async (state) => {
		const nowOffline = state.isOffline;

		// Update reactive state
		isOffline.value = nowOffline;
		connectionQuality.value = state.quality || offlineState.getConnectionQuality();

		// Auto-sync when transitioning from offline to online
		if (wasOffline && !nowOffline) {
			log.info("Transition to online detected, auto-syncing pending invoices");
			try {
				await syncPending();
			} catch (error) {
				log.error("Auto-sync failed on reconnection", error);
			}
		}

		wasOffline = nowOffline;
	});

	// =========================================================================
	// COMPUTED
	// =========================================================================

	/** Whether there are any pending invoices to sync */
	const hasPendingInvoices = computed(() => pendingInvoicesCount.value > 0);

	// =========================================================================
	// INTERNAL HELPERS
	// =========================================================================

	/**
	 * Update the pending invoices count from the worker
	 */
	async function updatePendingCount() {
		try {
			pendingInvoicesCount.value = await offlineWorker.getOfflineInvoiceCount();
		} catch (error) {
			log.error("Failed to get pending invoice count", error);
		}
	}

	/**
	 * Sync pending invoices to the server
	 * @throws {Error} If called while offline
	 */
	async function syncPending() {
		if (isOffline.value) {
			throw new Error("Cannot sync while offline");
		}

		isSyncing.value = true;
		try {
			const result = await syncOfflineInvoices();
			await updatePendingCount();
			return result;
		} catch (error) {
			log.error("Failed to sync invoices", error);
			throw error;
		} finally {
			isSyncing.value = false;
		}
	}

	/**
	 * Get all pending invoices from the worker
	 */
	async function getPending() {
		return await offlineWorker.getOfflineInvoices();
	}

	/**
	 * Delete a pending invoice by ID
	 * @param {string} id - Invoice ID to delete
	 */
	async function deletePending(id) {
		// Before removing the queued invoice, release any one-time-per-customer
		// redemptions it cached locally so a void doesn't permanently block the
		// customer from the offer (mirrors the server's release on cancel).
		try {
			const pending = await getPending();
			const row = pending.find((inv) => inv.id === id || inv.offline_id === id);
			const offlineId = row?.offline_id || row?.data?.offline_id;
			if (offlineId) {
				await releaseOfflineRedemptions(offlineId, row?.data?.customer || null);
			}
		} catch (error) {
			log.error("Failed to release offline redemptions for deleted invoice", error);
		}
		await offlineWorker.deleteOfflineInvoice(id);
		await updatePendingCount();
	}

	/**
	 * Mark a queued offline invoice as superseded (by an edit) and release the
	 * one-time-per-customer redemptions it cached. The superseded row never syncs,
	 * so its redemptions must be freed; the replacement records its own. Bundling
	 * release with supersede here keeps it on a single chokepoint, mirroring delete.
	 * @param {number} queueId - invoice_queue id of the superseded row
	 * @param {string} replacedBy - id/name of the replacement invoice (audit trail)
	 * @param {string} [offlineId] - offline_id of the superseded row (its redemption key)
	 * @param {string} [customer] - customer of the superseded row, if known
	 */
	async function supersedeInvoice(queueId, replacedBy, offlineId = null, customer = null) {
		await offlineWorker.supersedeOfflineInvoice(queueId, replacedBy);
		if (offlineId) {
			try {
				await releaseOfflineRedemptions(offlineId, customer);
			} catch (error) {
				log.error("Failed to release offline redemptions for superseded invoice", error);
			}
		}
		await updatePendingCount();
	}

	/**
	 * Cache items and customers for offline use
	 * @param {Array} items - Items to cache
	 * @param {Array} customers - Customers to cache
	 */
	async function cacheData(items, customers) {
		try {
			if (items?.length > 0) {
				await offlineWorker.cacheItems(items);
			}
			if (customers?.length > 0) {
				await offlineWorker.cacheCustomers(customers);
			}
			return true;
		} catch (error) {
			log.error("Failed to cache data", error);
			return false;
		}
	}

	// =========================================================================
	// PUBLIC ACTIONS
	// =========================================================================

	/**
	 * Save an invoice offline for later sync
	 * @param {Object} invoiceData - Invoice data to save
	 */
	async function saveInvoiceOffline(invoiceData) {
		try {
			const result = await offlineWorker.saveOfflineInvoice(invoiceData);
			await updatePendingCount();
			log.info("Invoice saved offline successfully");
			return result || { success: true };
		} catch (error) {
			log.error("Failed to save invoice offline", error);
			throw error;
		}
	}

	/**
	 * Load the list of pending invoices for display
	 */
	async function loadPendingInvoices() {
		try {
			pendingInvoicesList.value = await getPending();
		} catch (error) {
			log.error("Failed to load pending invoices", error);
			pendingInvoicesList.value = [];
		}
	}

	/**
	 * Delete an offline invoice by ID with user feedback
	 * @param {string} invoiceId - Invoice ID to delete
	 */
	async function deleteOfflineInvoice(invoiceId) {
		try {
			await deletePending(invoiceId);
			await loadPendingInvoices();
			showSuccess(__("Offline invoice deleted successfully"));
		} catch (error) {
			log.error("Failed to delete offline invoice", error);
			showError(error.message || __("Failed to delete offline invoice"));
			throw error;
		}
	}

	/**
	 * Sync all pending invoices with user feedback
	 * @returns {Object} Sync result with success/failed counts
	 */
	async function syncAllPending() {
		if (isOffline.value) {
			showWarning(__("Cannot sync while offline"));
			return { success: 0, failed: 0, errors: [] };
		}

		try {
			const result = await syncPending();

			if (result.success > 0) {
				showSuccess(__("{0} invoice(s) synced successfully", [result.success]));
				await loadPendingInvoices();
			}

			return result;
		} catch (error) {
			log.error("Sync all pending failed", error);
			throw error;
		}
	}

	/**
	 * Preload data for offline use (payment methods, customers)
	 * @param {Object} currentProfile - Current POS profile
	 */
	let _preloadingProfile = null;
	async function preloadDataForOffline(currentProfile) {
		if (!currentProfile || isOffline.value) {
			return;
		}

		// Prevent duplicate concurrent preloads (e.g., from component remounts
		// triggered by language/translation version changes)
		if (_preloadingProfile === currentProfile.name) {
			log.debug("Preload already in progress for this profile, skipping duplicate");
			return;
		}
		_preloadingProfile = currentProfile.name;

		try {
			const cacheReady = await checkCacheReady();
			const stats = await getCacheStats();
			const needsRefresh =
				!stats.lastSync || Date.now() - stats.lastSync > 24 * 60 * 60 * 1000;

			// Always load payment methods for reliable offline support
			log.info("Loading payment methods for offline use");
			try {
				const paymentMethodsData = await cachePaymentMethodsFromServer(
					currentProfile.name
				);

				if (paymentMethodsData.payment_methods?.length > 0) {
					const methodsWithProfile = paymentMethodsData.payment_methods.map(
						(method) => ({
							...method,
							pos_profile: currentProfile.name,
						})
					);
					await offlineWorker.cachePaymentMethods(methodsWithProfile);
					log.success(`Cached ${methodsWithProfile.length} payment methods`);
				}
			} catch (error) {
				log.error("Failed to load payment methods", error);
				// Continue with other data loading
			}

			// Cache sales persons for offline use
			try {
				const salesPersonsData = await cacheSalesPersonsFromServer(currentProfile.name);
				if (salesPersonsData.sales_persons?.length > 0) {
					const personsWithProfile = salesPersonsData.sales_persons.map((person) => ({
						...person,
						pos_profile: currentProfile.name,
					}));
					await offlineWorker.cacheSalesPersons(personsWithProfile);
					log.success(`Cached ${personsWithProfile.length} sales persons`);
				}
			} catch (error) {
				log.error("Failed to load sales persons", error);
			}

			// Load customers if cache needs refresh
			if (!cacheReady || needsRefresh) {
				showSuccess(__("Loading customers for offline use..."));

				const customersData = await cacheCustomersFromServer(currentProfile.name);
				await cacheData([], customersData.customers || []);

				showSuccess(__("Data is ready for offline use"));
			}

			// Preload invoice history and unpaid invoices in parallel for faster startup
			log.info("Loading invoice data for offline use");
			try {
				const [invoices, unpaidInvoices, unpaidSummary] = await Promise.all([
					call("pos_next.api.invoices.get_invoices", {
						pos_profile: currentProfile.name,
						limit: 100,
					}).catch((err) => {
						log.error("Failed to load invoice history", err);
						return [];
					}),
					call("pos_next.api.partial_payments.get_unpaid_invoices", {
						pos_profile: currentProfile.name,
						limit: 100,
					}).catch((err) => {
						log.error("Failed to load unpaid invoices", err);
						return [];
					}),
					call("pos_next.api.partial_payments.get_unpaid_summary", {
						pos_profile: currentProfile.name,
					}).catch((err) => {
						log.error("Failed to load unpaid summary", err);
						return null;
					}),
				]);

				// Cache results in parallel
				await Promise.all([
					invoices?.length > 0
						? cacheInvoiceHistory(invoices, currentProfile.name).then(() =>
								log.success(
									`Cached ${invoices.length} invoices for offline viewing`
								)
						  )
						: Promise.resolve(),
					unpaidInvoices?.length > 0
						? cacheUnpaidInvoices(unpaidInvoices, currentProfile.name).then(() =>
								log.success(
									`Cached ${unpaidInvoices.length} unpaid invoices for offline viewing`
								)
						  )
						: Promise.resolve(),
					unpaidSummary
						? cacheUnpaidSummary(unpaidSummary, currentProfile.name).then(() =>
								log.debug("Cached unpaid invoice summary")
						  )
						: Promise.resolve(),
				]);
			} catch (error) {
				log.error("Failed to load invoice data for offline", error);
				// Continue - not critical for POS operation
			}
		} catch (error) {
			log.error("Failed to preload offline data", error);
			showWarning(__("Some data may not be available offline"));
		} finally {
			_preloadingProfile = null;
		}
	}

	/**
	 * Check if offline cache is available and warn user if not
	 * @returns {boolean} Whether cache is ready
	 */
	async function checkOfflineCacheAvailability() {
		const cacheReady = await checkCacheReady();
		if (!cacheReady && isOffline.value) {
			showWarning(__("POS is offline without cached data. Please connect to sync."));
		}
		return cacheReady;
	}

	/**
	 * Check if the offline cache is ready
	 */
	async function checkCacheReady() {
		return await offlineWorker.isCacheReady();
	}

	/**
	 * Get cache statistics
	 */
	async function getCacheStats() {
		return await offlineWorker.getCacheStats();
	}

	// =========================================================================
	// INITIALIZATION
	// =========================================================================

	// Initialize pending count on store creation
	updatePendingCount();

	// =========================================================================
	// EXPORTS
	// =========================================================================

	return {
		// State
		isOffline,
		pendingInvoicesCount,
		isSyncing,
		pendingInvoicesList,

		// Computed
		hasPendingInvoices,

		// Actions
		saveInvoiceOffline,
		loadPendingInvoices,
		updatePendingCount,
		deleteOfflineInvoice,
		supersedeInvoice,
		syncAllPending,
		preloadDataForOffline,
		checkOfflineCacheAvailability,
		checkCacheReady,
		getCacheStats,
	};
});
