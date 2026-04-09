/**
 * Customer Display Sync Composable
 *
 * Watches cart changes and syncs them to the customer display API.
 * This composable should be used in the main POS component (POSSale.vue).
 *
 * Features:
 * - Debounced cart sync to avoid excessive API calls
 * - Automatic sync on cart changes
 * - Sale complete notification
 * - Cart clear on session close
 * - Customer created notification (from display)
 */

import { createResource } from "frappe-ui"
import { ref, watch, onUnmounted, toRaw } from "vue"
import { usePOSCartStore } from "@/stores/posCart"
import { logger } from "@/utils/logger"

const log = logger.create("CustomerDisplaySync")

// Event handler for customer created from display
let customerCreatedHandler = null

// Debounce delay for cart sync
const SYNC_DEBOUNCE_MS = 300

// Track if sync is enabled
const isSyncEnabled = ref(false)
const currentPosOpeningEntry = ref(null)

// Sync resources
const updateCartResource = createResource({
	url: "pos_next.api.customer_display.update_cart_data",
	auto: false,
})

const clearCartResource = createResource({
	url: "pos_next.api.customer_display.clear_cart_cache",
	auto: false,
})

const notifySaleCompleteResource = createResource({
	url: "pos_next.api.customer_display.notify_sale_complete",
	auto: false,
})

/**
 * Build cart data payload for customer display
 */
function buildCartPayload(cartStore, currency ) {
	const items = toRaw(cartStore.invoiceItems).map((item) => ({
		item_code: item.item_code,
		item_name: item.item_name,
		qty: item.quantity || item.qty || 0,
		rate: item.rate || 0,
		amount: item.amount || 0,
		uom: item.uom || item.stock_uom || "Unit",
		discount_percentage: item.discount_percentage || 0,
		image: item.image || null,
	}))

	return {
		items,
		customer: cartStore.customer?.name || cartStore.customer || null,
		customer_name: cartStore.customer?.customer_name || null,
		subtotal: cartStore.subtotal || 0,
		total_tax: cartStore.totalTax || 0,
		discount_amount: cartStore.totalDiscount || 0,
		grand_total: cartStore.grandTotal || 0,
		currency: currency,
	}
}

/**
 * Sync cart data to customer display
 */
async function syncCartToDisplay(cartStore, currency) {
	if (!isSyncEnabled.value || !currentPosOpeningEntry.value) {
		return
	}

	try {
		const cartData = buildCartPayload(cartStore, currency)

		await updateCartResource.fetch({
			pos_opening_entry: currentPosOpeningEntry.value,
			cart_data: JSON.stringify(cartData),
		})

		log.debug("Cart synced to display", { itemCount: cartData.items.length })
	} catch (error) {
		log.error("Failed to sync cart to display", error)
	}
}

/**
 * Notify display that sale is complete
 */
async function notifySaleComplete(grandTotal = 0, invoiceName = null) {
	if (!isSyncEnabled.value || !currentPosOpeningEntry.value) {
		return
	}

	try {
		await notifySaleCompleteResource.fetch({
			pos_opening_entry: currentPosOpeningEntry.value,
			invoice_name: invoiceName,
			grand_total: grandTotal,
		})

		log.info("Sale complete notification sent")
	} catch (error) {
		log.error("Failed to notify sale complete", error)
	}
}

/**
 * Clear display cart (on session close or manual clear)
 */
async function clearDisplayCart() {
	if (!currentPosOpeningEntry.value) {
		return
	}

	try {
		await clearCartResource.fetch({
			pos_opening_entry: currentPosOpeningEntry.value,
		})

		log.info("Display cart cleared")
	} catch (error) {
		log.error("Failed to clear display cart", error)
	}
}

// Customer created callback storage
let onCustomerCreatedCallback = null

/**
 * Main composable
 */
export function useCustomerDisplaySync() {
	const cartStore = usePOSCartStore()
	let debounceTimer = null
	let watcherCleanup = null

	/**
	 * Enable cart sync for a POS session
	 * @param {string} posOpeningEntry - POS Opening Entry name
	 * @param {string} currency - Currency code
	 */
	function enableSync(posOpeningEntry, currency) {
		if (!posOpeningEntry) {
			log.warn("Cannot enable sync without POS opening entry")
			return
		}

		currentPosOpeningEntry.value = posOpeningEntry
		isSyncEnabled.value = true

		// Setup watchers for cart changes
		setupWatchers(currency)

		// Setup listener for customer created from display
		setupCustomerCreatedListener(posOpeningEntry)

		// Do initial sync
		syncCartToDisplay(cartStore, currency)

		log.info("Customer display sync enabled", { posOpeningEntry })
	}

	/**
	 * Disable cart sync
	 */
	function disableSync() {
		isSyncEnabled.value = false

		// Clear any pending debounced sync
		if (debounceTimer) {
			clearTimeout(debounceTimer)
			debounceTimer = null
		}

		// Cleanup watchers
		if (watcherCleanup) {
			watcherCleanup()
			watcherCleanup = null
		}

		// Cleanup customer created listener
		cleanupCustomerCreatedListener()

		log.info("Customer display sync disabled")
	}

	/**
	 * Setup listener for customer created from display
	 * @param {string} posOpeningEntry - POS Opening Entry name
	 */
	function setupCustomerCreatedListener(posOpeningEntry) {
		// Cleanup existing listener first
		cleanupCustomerCreatedListener()

		log.info("Setting up customer created listener", {
			posOpeningEntry,
			hasRealtime: !!window.frappe?.realtime,
			realtimeConnected: window.frappe?.realtime?.socket?.connected,
		})

		if (!window.frappe?.realtime) {
			log.warn("Socket.IO not available for customer created listener")
			return
		}

		const eventName = `customer_created_${posOpeningEntry}`
		log.info("Registering Socket.IO listener", { eventName })

		customerCreatedHandler = (data) => {
			log.info("Socket.IO event received", {
				eventName,
				data,
				hasCallback: !!onCustomerCreatedCallback,
			})

			// Only process if created from customer display
			if (data.created_from !== "customer_display") {
				log.debug("Ignoring event - not from customer display", {
					created_from: data.created_from,
				})
				return
			}

			log.info("Customer created from display", {
				name: data.name,
				customerName: data.customer_name,
			})

			// Call the registered callback if any
			if (onCustomerCreatedCallback) {
				log.info("Calling onCustomerCreatedCallback")
				onCustomerCreatedCallback(data)
			} else {
				log.warn("No callback registered for customer created event")
			}
		}

		window.frappe.realtime.on(eventName, customerCreatedHandler)
		log.info("Customer created listener registered successfully", { eventName })
	}

	/**
	 * Cleanup customer created listener
	 */
	function cleanupCustomerCreatedListener() {
		if (!customerCreatedHandler || !currentPosOpeningEntry.value) {
			return
		}

		if (window.frappe?.realtime) {
			const eventName = `customer_created_${currentPosOpeningEntry.value}`
			window.frappe.realtime.off(eventName, customerCreatedHandler)
			log.debug("Customer created listener cleaned up")
		}

		customerCreatedHandler = null
	}

	/**
	 * Register callback for when customer is created from display
	 * @param {Function} callback - Callback function: (customerData) => void
	 */
	function onCustomerCreated(callback) {
		if (typeof callback !== "function") {
			throw new TypeError("Callback must be a function")
		}
		onCustomerCreatedCallback = callback
		log.info("Customer created callback registered")
	}

	/**
	 * Setup watchers for cart changes
	 */
	function setupWatchers(currency) {
		// Cleanup existing watchers
		if (watcherCleanup) {
			watcherCleanup()
		}

		// Watch for cart changes (items, customer, totals)
		const unwatch = watch(
			[
				() => cartStore.invoiceItems.length,
				() =>
					cartStore.invoiceItems
						.map((i) => `${i.item_code}:${i.quantity}:${i.rate}`)
						.join(","),
				() => cartStore.customer?.name || cartStore.customer,
				() => cartStore.grandTotal,
				() => cartStore.totalDiscount,
			],
			() => {
				// Debounced sync
				if (debounceTimer) {
					clearTimeout(debounceTimer)
				}

				debounceTimer = setTimeout(() => {
					syncCartToDisplay(cartStore, currency)
				}, SYNC_DEBOUNCE_MS)
			},
			{ deep: false },
		)

		watcherCleanup = unwatch
	}

	/**
	 * Manually trigger cart sync
	 */
	function forceSync(currency) {
		syncCartToDisplay(cartStore, currency)
	}

	// Cleanup on unmount
	onUnmounted(() => {
		disableSync()
	})

	return {
		// State
		isSyncEnabled,
		currentPosOpeningEntry,

		// Actions
		enableSync,
		disableSync,
		forceSync,
		notifySaleComplete,
		clearDisplayCart,

		// Customer created from display
		onCustomerCreated,
	}
}
