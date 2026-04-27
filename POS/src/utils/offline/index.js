// Main offline module - exports all offline functionality

export { db, initDB, checkDBHealth, getSetting, setSetting } from "./db"

// Centralized offline state manager (single source of truth)
export {
	offlineState,
	isOffline,
	setManualOffline,
	toggleManualOffline,
	getOfflineState,
	checkConnectivity,
	getConnectionQuality,
} from "./offlineState"

export {
	pingServer,
	saveOfflineInvoice,
	getOfflineInvoices,
	getOfflineInvoiceCount,
	syncOfflineInvoices,
	deleteOfflineInvoice,
	updateLocalStock,
	getLocalStock,
	saveOfflinePayment,
	cacheInvoiceHistory,
	getCachedInvoiceHistory,
	clearInvoiceHistoryCache,
	cacheUnpaidInvoices,
	getCachedUnpaidInvoices,
	cacheUnpaidSummary,
	getCachedUnpaidSummary,
} from "./sync"

export {
	cacheItems,
	getCachedItems,
	searchCachedItems as searchCachedItemsOld,
	getItemByBarcode,
	getItemWithPrice,
	cacheCustomers,
	searchCachedCustomers as searchCachedCustomersOld,
	getItemsLastSync,
	getCustomersLastSync,
	isCacheFresh,
	clearItemsCache,
	clearCustomersCache,
} from "./items"

// New cache system exports (excluding setManualOffline/toggleManualOffline - use offlineState instead)
export {
	memory,
	initMemoryCache,
	isCacheReady,
	isStockCacheReady,
	isManualOffline,
	cacheItemsFromServer,
	cacheCustomersFromServer,
	refreshCustomerExtrasFromServer,
	cachePaymentMethodsFromServer,
	getCachedPaymentMethods,
	cacheSalesPersonsFromServer,
	getCachedSalesPersons,
	searchCachedItems,
	searchCachedCustomers,
	getCachedItem,
	getCachedCustomer,
	needsCacheRefresh,
	clearAllCache,
	getCacheStats,
	cacheTaxesFromServer,
	getCachedTaxes,
	cacheUomsFromServer,
	getCachedUoms,
	cacheLoyaltyProgramsFromServer,
	getCachedLoyaltyPrograms,
	cacheItemGroupsFromServer,
	getCachedItemGroups,
	cacheBrandsFromServer,
	getCachedBrands,
	cacheOfflineBundleFromServer,
} from "./cache"

// Offline customer create queue
export {
	enqueueOfflineCustomer,
	getQueuedOfflineCustomers,
	syncOfflineCustomers,
} from "./customerQueue"

// Image prefetch for fully-offline image rendering
export {
	prefetchItemImages,
	resetImagePrefetchProgress,
	cancelImagePrefetch,
} from "./imagePrefetch"

// Browser-level "don't evict me" flag
export {
	requestPersistentStorage,
	ensurePersistentStorage,
	getPersistenceStatus,
} from "./persistence"

// QZ-Tray-backed on-disk mirror — survives browser wipes
export {
	mirrorOfflineInvoice,
	mirrorOfflineCustomer,
	removeMirroredInvoice,
	removeMirroredCustomer,
	restoreFromDisk,
	backfillMirrorFromIndexedDB,
	isMirrorAvailable,
	enableDiskMirror,
	disableDiskMirror,
} from "./diskBackup"
