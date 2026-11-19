import { ref } from "vue";

/**
 * Opening the payment dialog re-checks the price first (Ruling 101).
 *
 * Online, the cart is saved as an unpaid draft and the server re-prices Friends &
 * Family to the customer's remaining allowance. An unchanged total opens payment
 * directly; a changed one waits for the cashier to confirm it (`pendingChange`),
 * so a "Block submit" cap refusal never comes after the money is taken. Offline
 * sales open payment without a check (they are only logged).
 *
 * @param {Object} deps
 * @param {() => boolean} deps.isOffline
 * @param {() => Promise<{changed: boolean, alreadySubmitted?: boolean, previousTotal?: number, total?: number}>} deps.checkPrice
 * @param {() => void} deps.openPayment
 * @param {(error: unknown) => void} deps.showError
 */
export function usePaymentOpenCheck({ isOffline, checkPrice, openPayment, showError }) {
	const checking = ref(false);
	// { previousTotal, total, message } while the cashier is asked to confirm a new total
	const pendingChange = ref(null);

	/** Run the check; a failed check rejects. */
	async function runCheck() {
		checking.value = true;
		try {
			return await checkPrice();
		} finally {
			checking.value = false;
		}
	}

	/** The cashier asked for payment. Resolves true when the payment dialog opened. */
	async function requestPayment() {
		if (checking.value) return false;
		if (isOffline()) {
			openPayment();
			return true;
		}
		let check;
		try {
			check = await runCheck();
		} catch (error) {
			showError(error);
			return false;
		}
		// The cart was sold before (a restored draft, Ruling 136): no payment for it.
		if (check?.alreadySubmitted) return false;
		if (check?.changed) {
			pendingChange.value = {
				previousTotal: check.previousTotal,
				total: check.total,
				message: check.message || "",
			};
			return false;
		}
		openPayment();
		return true;
	}

	/** The cashier accepted the new total. */
	function confirmChange() {
		pendingChange.value = null;
		openPayment();
	}

	function cancelChange() {
		pendingChange.value = null;
	}

	/**
	 * The server refused the submit (e.g. a "Block submit" F&F cap): the cart is kept
	 * and the check runs again. Resolves true when the total changed: the cashier is
	 * then asked to confirm it, with the server's `message`; otherwise the caller shows
	 * the error as usual.
	 */
	async function recheckAfterRefusal(message = "") {
		if (isOffline() || checking.value) return false;
		let check;
		try {
			check = await runCheck();
		} catch {
			return false; // the refusal itself is still shown by the caller
		}
		if (check?.alreadySubmitted) return true; // the cart was closed as sold; no refusal to show
		if (!check?.changed) return false;
		pendingChange.value = {
			previousTotal: check.previousTotal,
			total: check.total,
			message: [message, check.message].filter(Boolean).join(" "),
		};
		return true;
	}

	return {
		checking,
		pendingChange,
		requestPayment,
		confirmChange,
		cancelChange,
		recheckAfterRefusal,
	};
}
