/**
 * Idempotency key for online invoice checkout.
 *
 * The client gives up on a submit after 60s (see CoalescingMutex) but the server
 * keeps working and may still commit the invoice. If the cashier retries, the
 * retry must carry the same key so the server returns the invoice that was
 * created instead of creating a second one.
 *
 * The key is stable while the payload is unchanged and rotates as soon as the
 * cart, customer, payments or discounts change, so an edited sale is never
 * mistaken for the earlier one.
 */

const defaultMakeId = () => `pos_online_${globalThis.crypto.randomUUID()}`;

export function createSubmitRequestTracker(makeId = defaultMakeId) {
	let currentId = null;
	let currentFingerprint = null;
	let currentDraft = null;

	return {
		/** Key for this payload; reused only if the payload is identical to the last one. */
		idFor(payload) {
			const fingerprint = JSON.stringify(payload);
			if (currentId === null || fingerprint !== currentFingerprint) {
				currentId = makeId();
				currentFingerprint = fingerprint;
				currentDraft = null; // a draft belongs to one payload only
			}
			return currentId;
		},
		/**
		 * Remember the server draft created for the current payload, so a manual retry of the
		 * SAME unchanged cart goes straight to submit instead of creating (and orphaning) another
		 * draft and taking another invoice-number lock.
		 */
		rememberDraft(draft) {
			currentDraft = draft || null;
		},
		/** The draft created for the current payload, or null. */
		draft() {
			return currentDraft;
		},
		/** The key of the checkout in progress (null before the first submit / after reset). */
		current() {
			return currentId;
		},
		/** Call after a confirmed success (or when the cart is cleared). */
		reset() {
			currentId = null;
			currentFingerprint = null;
			currentDraft = null;
		},
	};
}

/** True for the "Operation timed out after Nms" error raised by the submit mutex. */
export function isSubmitTimeoutError(error) {
	return /timed out after \d+ms/i.test(error?.message || "");
}
