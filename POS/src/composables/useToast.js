import { ref, computed } from "vue"

// Toast timing constants
const TOAST_DURATION = 4000 // Auto-hide after 4 seconds
const TOAST_FADE_DURATION = 300 // Fade animation duration
const TOAST_QUEUE_DELAY = 300 // Delay between queued toasts

// Global toast state
const toastQueue = ref([])
const currentToast = ref(null)
const showToast = ref(false)
let toastTimer = null
let isProcessing = false

// For backward compatibility
const toastNotification = computed(() => currentToast.value)

function processQueue() {
	if (isProcessing || toastQueue.value.length === 0) {
		return
	}

	isProcessing = true
	currentToast.value = toastQueue.value.shift()
	showToast.value = true

	// Clear any existing timer
	if (toastTimer) {
		clearTimeout(toastTimer)
	}

	// Auto-hide after duration
	toastTimer = setTimeout(() => {
		showToast.value = false
		setTimeout(() => {
			currentToast.value = null
			isProcessing = false
			// Process next toast in queue
			if (toastQueue.value.length > 0) {
				setTimeout(processQueue, TOAST_QUEUE_DELAY)
			}
		}, TOAST_FADE_DURATION)
	}, TOAST_DURATION)
}

export function useToast() {
	function showToastNotification(title, message, type = "success") {
		// Add to queue
		toastQueue.value.push({ title, message, type })
		// Start processing if not already
		processQueue()
	}

	function showSuccess(message) {
		showToastNotification(__("Success"), message, "success")
	}

	function showError(message) {
		showToastNotification(__("Error"), message, "error")
	}

	function showWarning(message) {
		showToastNotification(__("Validation Error"), message, "warning")
	}

	function showInfo(message) {
		showToastNotification(__("Info"), message, "info")
	}

	function hideToast() {
		if (toastTimer) {
			clearTimeout(toastTimer)
			toastTimer = null
		}
		showToast.value = false
		setTimeout(() => {
			currentToast.value = null
			isProcessing = false
			// Process next toast in queue
			if (toastQueue.value.length > 0) {
				setTimeout(processQueue, TOAST_QUEUE_DELAY)
			}
		}, TOAST_FADE_DURATION)
	}

	function clearAllToasts() {
		if (toastTimer) {
			clearTimeout(toastTimer)
			toastTimer = null
		}
		toastQueue.value = []
		showToast.value = false
		currentToast.value = null
		isProcessing = false
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
		hideToast,
		clearAllToasts,
	}
}
