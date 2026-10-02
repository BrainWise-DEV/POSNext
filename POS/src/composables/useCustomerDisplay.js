/**
 * Customer Display Composable (POS side)
 *
 * Mirrors the cart to the customer-facing display window and announces
 * completed payments. See utils/customerDisplay.js for the protocol.
 *
 * @example
 * ```js
 * const customerDisplay = useCustomerDisplay()
 * customerDisplay.open()                                // from a user click
 * customerDisplay.showPaymentComplete(paymentData, total) // before clearing the cart
 * ```
 */

import { useFormatters } from "@/composables/useFormatters"
import { usePOSCartStore } from "@/stores/posCart"
import { usePOSShiftStore } from "@/stores/posShift"
import { formatCurrency } from "@/utils/currency"
import {
	CUSTOMER_DISPLAY_WINDOW_NAME,
	DisplayMessage,
	openCustomerDisplayChannel,
} from "@/utils/customerDisplay"
import { logger } from "@/utils/logger"
import { computed, onUnmounted, ref, watch } from "vue"
import { useRouter } from "vue-router"

const log = logger.create("CustomerDisplay")

export function useCustomerDisplay() {
	const cartStore = usePOSCartStore()
	const shiftStore = usePOSShiftStore()
	const router = useRouter()
	const { formatQuantity } = useFormatters()

	// Snapshots are only built once a display has announced itself
	const displayConnected = ref(false)

	const channel = openCustomerDisplayChannel(({ type }) => {
		if (type !== DisplayMessage.DISPLAY_READY) return

		if (displayConnected.value) {
			// A display (re)loaded - resend the current state
			publishCart()
		} else {
			log.info("Customer display connected")
			displayConnected.value = true // cartSnapshot watcher publishes
		}
	})

	function format(value) {
		return formatCurrency(Number(value) || 0, shiftStore.profileCurrency)
	}

	// Mirrors the totals shown in InvoiceCart so cashier and customer see the same numbers
	const cartSnapshot = computed(() => {
		if (!displayConnected.value) return null

		const items = cartStore.invoiceItems
		const subtotal = cartStore.taxInclusive
			? cartStore.subtotal - cartStore.totalTax
			: cartStore.subtotal

		return {
			storeName: shiftStore.profileCompany || "",
			items: items.map((item, index) => ({
				key: `${item.item_code}:${item.uom || ""}:${index}`,
				name: item.item_name || item.item_code,
				quantity: formatQuantity(item.quantity),
				freeQuantity: item.free_qty > 0 ? formatQuantity(item.free_qty) : null,
				uom: item.uom || item.stock_uom || "",
				rate: format(item.rate),
				discount:
					item.discount_amount > 0 ? format(item.discount_amount) : null,
				amount: format(item.amount || item.rate * item.quantity),
			})),
			totalQuantity: formatQuantity(
				items.reduce(
					(sum, item) => sum + (item.quantity || 0) + (item.free_qty || 0),
					0,
				),
			),
			subtotal: format(subtotal),
			discount:
				cartStore.totalDiscount > 0 ? format(cartStore.totalDiscount) : null,
			tax: cartStore.totalTax > 0 ? format(cartStore.totalTax) : null,
			grandTotal: format(cartStore.grandTotal),
		}
	})

	function publishCart() {
		if (channel && cartSnapshot.value) {
			channel.post(DisplayMessage.CART_UPDATED, cartSnapshot.value)
		}
	}

	watch(cartSnapshot, publishCart)

	/**
	 * Show the "Thank You" screen. Call before clearing the cart - the empty
	 * cart that follows is ignored by the display until the screen times out.
	 * @param {Object} paymentData - Payload emitted by PaymentDialog
	 * @param {number} grandTotal - Invoice grand total
	 */
	function showPaymentComplete(paymentData, grandTotal) {
		if (!channel || !displayConnected.value) return

		const changeAmount = paymentData?.change_amount || 0
		const outstandingAmount = paymentData?.outstanding_amount || 0

		channel.post(DisplayMessage.PAYMENT_COMPLETED, {
			paidAmount: format(paymentData?.paid_amount ?? grandTotal),
			grandTotal: format(grandTotal),
			changeAmount: changeAmount > 0 ? format(changeAmount) : null,
			outstandingAmount:
				outstandingAmount > 0 ? format(outstandingAmount) : null,
		})
	}

	/**
	 * Open (or re-focus) the customer display window. Must be called from a
	 * user gesture, otherwise the browser blocks the popup.
	 * @returns {boolean} - false if the popup was blocked or unsupported
	 */
	function open() {
		if (!channel) return false

		const url = router.resolve({ name: "CustomerDisplay" }).href
		const displayWindow = window.open(
			url,
			CUSTOMER_DISPLAY_WINDOW_NAME,
			"popup,width=1280,height=800",
		)
		if (!displayWindow) return false

		displayWindow.focus()
		return true
	}

	// Don't leave the last customer's cart on screen once the POS goes away
	function resetDisplay() {
		if (channel && displayConnected.value) {
			channel.post(DisplayMessage.CART_UPDATED, {
				...cartSnapshot.value,
				items: [],
			})
		}
	}

	window.addEventListener("pagehide", resetDisplay)
	channel?.post(DisplayMessage.POS_READY)

	onUnmounted(() => {
		window.removeEventListener("pagehide", resetDisplay)
		resetDisplay()
		channel?.close()
	})

	return {
		isSupported: !!channel,
		open,
		showPaymentComplete,
	}
}
