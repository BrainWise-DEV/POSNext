import { ref } from "vue"
import { playSuccessSound, playErrorSound } from "@/utils/soundFeedback"

// Global toast state
const toastNotification = ref(null)
const showToast = ref(false)

export function useToast() {
	function showToastNotification(title, message, type = "success") {
		toastNotification.value = { title, message, type }
		showToast.value = true

		// Auto-hide after 4 seconds
		setTimeout(() => {
			showToast.value = false
			setTimeout(() => {
				toastNotification.value = null
			}, 300) // Wait for fade animation
		}, 4000)
	}

	function showSuccess(message) {
		showToastNotification("Success", message, "success")
		playSuccessSound()
	}

	function showError(message) {
		showToastNotification("Error", message, "error")
		playErrorSound()
	}

	function showWarning(message) {
		showToastNotification("Validation Error", message, "warning")
		playErrorSound()
	}

	function hideToast() {
		showToast.value = false
		setTimeout(() => {
			toastNotification.value = null
		}, 300)
	}

	return {
		toastNotification,
		showToast,
		showSuccess,
		showError,
		showWarning,
		hideToast,
	}
}
