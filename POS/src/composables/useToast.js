import { ref, computed } from "vue";

// Toast timing constants
const TOAST_DURATION = 4000; // Auto-hide after 4 seconds
const TOAST_FADE_DURATION = 300; // Fade animation duration

// Global toast state: one toast at a time, the latest replaces it
const toastQueue = ref([]); // Kept for backward compatibility; always empty
const currentToast = ref(null);
const showToast = ref(false);
let toastTimer = null;

// For backward compatibility
const toastNotification = computed(() => currentToast.value);

function clearToastTimer() {
	if (toastTimer) {
		clearTimeout(toastTimer);
		toastTimer = null;
	}
}

export function useToast() {
	function showToastNotification(title, message, type = "success") {
		// Latest wins: replace whatever is showing and restart the timer
		clearToastTimer();
		currentToast.value = { title, message, type };
		showToast.value = true;
		toastTimer = setTimeout(hideToast, TOAST_DURATION);
	}

	function showSuccess(message) {
		showToastNotification(__("Success"), message, "success");
	}

	function showError(message) {
		showToastNotification(__("Error"), message, "error");
	}

	function showWarning(message) {
		showToastNotification(__("Warning"), message, "warning");
	}

	function showInfo(message) {
		showToastNotification(__("Info"), message, "info");
	}

	/** Strip Frappe's HTML message markup down to plain text for a toast. */
	function flattenMessage(value) {
		return String(value)
			.replace(/<br\s*\/?>/gi, " ")
			.replace(/<[^>]+>/g, "")
			.replace(/\s+/g, " ")
			.trim();
	}

	/**
	 * Pull a human-readable message out of a Frappe error.
	 *
	 * Two shapes matter:
	 *  - frappe-ui's call()/frappeRequest() reject with an Error whose
	 *    `.message` is only "<method> <exc_type>" (e.g. "…save_product
	 *    ValidationError"). The real text is on `.messages`, an array
	 *    frappe-ui has already parsed out of _server_messages.
	 *  - A raw fetch() gets the untouched response, where the same text is
	 *    still a JSON string in `_server_messages`.
	 *
	 * Checking only _server_messages misses every error raised through the
	 * app's `call` wrapper, which is nearly all of them.
	 */
	function parseErrorMessage(error) {
		if (!error) return "";

		// frappe-ui shape: already-parsed array of message strings.
		if (Array.isArray(error.messages) && error.messages.length > 0) {
			const seen = new Set();
			for (const entry of error.messages) {
				const text = flattenMessage(entry?.message ?? entry);
				if (text && !seen.has(text)) {
					seen.add(text);
					return text;
				}
			}
		}

		// Raw response shape: _server_messages is a JSON string of JSON strings.
		try {
			if (error._server_messages) {
				const messages = JSON.parse(error._server_messages);
				if (Array.isArray(messages) && messages.length > 0) {
					const first =
						typeof messages[0] === "string" ? JSON.parse(messages[0]) : messages[0];
					if (first?.message) return flattenMessage(first.message);
				}
			}
		} catch {
			// Fall through to the generic message below.
		}

		// error.message is a useful fallback for plain Errors, but frappe-ui's
		// "<method> <exc_type>" string tells the user nothing.
		const message = error.message ? String(error.message) : "";
		if (message && error.exc_type && message.includes(error.exc_type)) return "";
		return message;
	}

	/**
	 * Show an error toast, preferring the server's own explanation.
	 * Never throws — an error handler that throws turns a failed action into a
	 * silent one.
	 */
	function handleError(error, defaultMessage = __("An error occurred")) {
		let message = defaultMessage;
		try {
			message = parseErrorMessage(error) || defaultMessage;
		} catch {
			message = defaultMessage;
		}
		showError(message);
	}

	function hideToast() {
		clearToastTimer();
		showToast.value = false;
		const hidden = currentToast.value;
		setTimeout(() => {
			// A newer toast may have replaced it during the fade
			if (currentToast.value === hidden && !showToast.value) currentToast.value = null;
		}, TOAST_FADE_DURATION);
	}

	function clearAllToasts() {
		clearToastTimer();
		showToast.value = false;
		currentToast.value = null;
	}

	return {
		// State
		toastNotification,
		showToast,
		toastQueue,

		// Actions
		showSuccess,
		showError,
		showWarning,
		showInfo,
		handleError,
		hideToast,
		clearAllToasts,
	};
}
