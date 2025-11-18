import { useOffline } from "@/composables/useOffline"
import { useToast } from "@/composables/useToast"
import { parseError } from "@/utils/errorHandler"
import {
	cacheCustomersFromServer,
	cachePaymentMethodsFromServer,
} from "@/utils/offline"
import { offlineWorker } from "@/utils/offline/workerClient"
import { defineStore } from "pinia"
import { computed, ref } from "vue"

export const usePOSSyncStore = defineStore("posSync", () => {
	// Use the existing offline composable
	const {
		isOffline,
		pendingInvoicesCount,
		isSyncing,
		saveInvoiceOffline,
		syncPending,
		getPending,
		deletePending,
		cacheData,
		checkCacheReady,
		getCacheStats,
	} = useOffline()

	// Use custom toast
	const { showSuccess, showError, showWarning } = useToast()

	// Additional offline state
	const pendingInvoicesList = ref([])

	// Computed
	const hasPendingInvoices = computed(() => pendingInvoicesCount.value > 0)

	// Actions
	async function loadPendingInvoices() {
		try {
			pendingInvoicesList.value = await getPending()
		} catch (error) {
			console.error("Error loading pending invoices:", error)
			pendingInvoicesList.value = []
		}
	}

	async function deleteOfflineInvoice(invoiceId) {
		try {
			await deletePending(invoiceId)
			await loadPendingInvoices()
			showSuccess("Offline invoice deleted successfully")
		} catch (error) {
			console.error("Error deleting offline invoice:", error)
			showError(error.message || "Failed to delete offline invoice")
			throw error
		}
	}

	async function syncAllPending() {
		if (isOffline.value) {
			showWarning("Cannot sync while offline")
			return { success: 0, failed: 0, errors: [] }
		}

		try {
			const result = await syncPending()

			if (result.success > 0) {
				showSuccess(`${result.success} invoice(s) synced successfully`)
				await loadPendingInvoices()
			}

			return result
		} catch (error) {
			console.error("Sync error:", error)
			throw error
		}
	}

	async function preloadDataForOffline(currentProfile) {
		if (!currentProfile || isOffline.value) {
			return
		}

		try {
			// Check cache status
			const cacheReady = await checkCacheReady()
			const stats = await getCacheStats()
			const needsRefresh =
				!stats.lastSync || Date.now() - stats.lastSync > 24 * 60 * 60 * 1000

			// ALWAYS load payment methods at startup for reliable offline support
			// This ensures payment modes are available even if cache is considered "ready"
			console.log('[POSSync] Loading payment methods for offline use...')
			try {
				const paymentMethodsData = await cachePaymentMethodsFromServer(currentProfile.name)

				// Cache payment methods using worker
				if (paymentMethodsData.payment_methods && paymentMethodsData.payment_methods.length > 0) {
					// Add pos_profile to each method for indexing
					const methodsWithProfile = paymentMethodsData.payment_methods.map((method) => ({
						...method,
						pos_profile: currentProfile.name,
					}))
					await offlineWorker.cachePaymentMethods(methodsWithProfile)
					console.log(`[POSSync] Cached ${methodsWithProfile.length} payment methods for offline use`)
				}
			} catch (error) {
				console.error('[POSSync] Error loading payment methods:', error)
				// Don't throw - continue with other data loading
			}

			if (!cacheReady || needsRefresh) {
				// NOTE: Items are now handled by itemStore's background sync
				// to prevent duplicate fetches and improve performance.
				// Only cache customers here (payment methods already loaded above).

				showSuccess("Loading customers for offline use...")

				// Fetch customers (items handled by itemStore, payment methods already loaded above)
				const customersData = await cacheCustomersFromServer(currentProfile.name)

				// Cache customers using composable
				await cacheData([], customersData.customers || [])

				showSuccess("Data is ready for offline use")
			}
		} catch (error) {
			console.error("Error pre-loading data:", error)
			showWarning("Some data may not be available offline")
		}
	}

	async function checkOfflineCacheAvailability() {
		const cacheReady = await checkCacheReady()
		if (!cacheReady && isOffline.value) {
			showWarning("POS is offline without cached data. Please connect to sync.")
		}
		return cacheReady
	}

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
		deleteOfflineInvoice,
		syncAllPending,
		preloadDataForOffline,
		checkOfflineCacheAvailability,
		checkCacheReady,
		getCacheStats,
	}
})
