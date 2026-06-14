import { ref, onUnmounted } from "vue"

/**
 * Composable for handling long press interactions
 * Supports both tap (short press) and long press actions
 * Uses PointerEvents for unified mouse/touch handling
 *
 * @param {Object} options - Configuration options
 * @param {number} options.duration - Long press duration in ms (default: 500)
 * @param {Function} options.onTap - Callback for tap/short press
 * @param {Function} options.onLongPress - Callback for long press
 * @returns {Object} - Event handlers and state
 */
export function useLongPress(options = {}) {
	const {
		duration = 500,
		onTap = null,
		onLongPress = null,
	} = options

	// State
	const isPressed = ref(false)
	const isLongPress = ref(false)
	let pressTimer = null
	let currentTarget = null

	// Clear any pending timer
	function clearPressTimer() {
		if (pressTimer) {
			clearTimeout(pressTimer)
			pressTimer = null
		}
	}

	// Handle pointer down - start long press detection
	function onPointerDown(event, target = null) {
		// Prevent default to avoid text selection
		event.preventDefault()

		isPressed.value = true
		isLongPress.value = false
		currentTarget = target

		// Start long press timer
		pressTimer = setTimeout(() => {
			isLongPress.value = true
			if (onLongPress && currentTarget !== null) {
				onLongPress(currentTarget)
			}
		}, duration)
	}

	// Handle pointer up - trigger tap if not long press
	function onPointerUp(target = null) {
		clearPressTimer()

		// If not a long press, trigger tap action
		if (isPressed.value && !isLongPress.value) {
			if (onTap) {
				onTap(target ?? currentTarget)
			}
		}

		// Reset state
		isPressed.value = false
		isLongPress.value = false
		currentTarget = null
	}

	// Handle pointer cancel/leave
	function onPointerCancel() {
		clearPressTimer()
		isPressed.value = false
		isLongPress.value = false
		currentTarget = null
	}

	// Cleanup on unmount
	onUnmounted(() => {
		clearPressTimer()
	})

	// Return handlers and state
	return {
		// State (reactive)
		isPressed,
		isLongPress,

		// Event handlers
		onPointerDown,
		onPointerUp,
		onPointerCancel,

		// Utility
		clearPressTimer,
	}
}

/**
 * Creates event handlers for a specific element with long press support
 * Useful for v-for loops where each item needs its own handlers
 *
 * @param {Object} options - Configuration options
 * @param {number} options.duration - Long press duration in ms (default: 500)
 * @returns {Object} - Factory function and state
 */
export function useLongPressHandlers(options = {}) {
	const { duration = 500 } = options

	// Shared state
	const pressState = ref({
		isPressed: false,
		isLongPress: false,
		currentTarget: null,
	})
	let pressTimer = null

	// Clear timer
	function clearTimer() {
		if (pressTimer) {
			clearTimeout(pressTimer)
			pressTimer = null
		}
	}

	// Create handlers for a target
	function createHandlers(onTap, onLongPress) {
		return {
			onPointerDown: (target, event) => {
				event.preventDefault()
				pressState.value.isPressed = true
				pressState.value.isLongPress = false
				pressState.value.currentTarget = target

				pressTimer = setTimeout(() => {
					pressState.value.isLongPress = true
					if (onLongPress) {
						onLongPress(target)
					}
				}, duration)
			},

			onPointerUp: (target) => {
				clearTimer()
				if (pressState.value.isPressed && !pressState.value.isLongPress) {
					if (onTap) {
						onTap(target)
					}
				}
				pressState.value.isPressed = false
				pressState.value.isLongPress = false
				pressState.value.currentTarget = null
			},

			onPointerCancel: () => {
				clearTimer()
				pressState.value.isPressed = false
				pressState.value.isLongPress = false
				pressState.value.currentTarget = null
			},
		}
	}

	// Cleanup
	onUnmounted(() => {
		clearTimer()
	})

	return {
		pressState,
		createHandlers,
		clearTimer,
	}
}
