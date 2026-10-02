/**
 * Customer Display Protocol
 *
 * Shared contract between the POS window and the customer-facing display
 * window (/pos/customer-display). Both run in the same browser, so they talk
 * over a BroadcastChannel - no server round-trip, and it keeps working offline.
 *
 * Handshake:
 * - The display posts DISPLAY_READY when it loads.
 * - The POS posts POS_READY when it loads, so an already-open display
 *   re-announces itself after a POS reload.
 * - The POS only starts publishing once it has heard from a display.
 *
 * Payloads are display-ready (amounts pre-formatted in the POS currency), so
 * the display window needs no POS profile or precision settings of its own.
 */

export const CUSTOMER_DISPLAY_CHANNEL = "pos-next-customer-display"
export const CUSTOMER_DISPLAY_WINDOW_NAME = "pos-next-customer-display"

/** How long the "Thank You" screen stays up before returning to the welcome screen */
export const PAYMENT_COMPLETE_DURATION_MS = 8000

export const DisplayMessage = Object.freeze({
	DISPLAY_READY: "display-ready",
	POS_READY: "pos-ready",
	CART_UPDATED: "cart-updated",
	PAYMENT_COMPLETED: "payment-completed",
})

export function isCustomerDisplaySupported() {
	return typeof BroadcastChannel !== "undefined"
}

/**
 * Open the customer display channel
 * @param {Function} onMessage - Called with `{ type, payload }` for each message
 * @returns {{ post: Function, close: Function } | null} - null if unsupported
 */
export function openCustomerDisplayChannel(onMessage) {
	if (!isCustomerDisplaySupported()) return null

	const channel = new BroadcastChannel(CUSTOMER_DISPLAY_CHANNEL)
	channel.onmessage = (event) => {
		if (event.data?.type) onMessage(event.data)
	}

	return {
		post(type, payload = {}) {
			channel.postMessage({ type, payload })
		},
		close() {
			channel.close()
		},
	}
}
