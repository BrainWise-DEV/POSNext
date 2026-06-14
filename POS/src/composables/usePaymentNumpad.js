/**
 * Payment Numpad Composable
 * Handles numeric keypad state, input, and keyboard support for payment dialog
 */

import { ref, computed, onMounted, onUnmounted } from "vue"

export function usePaymentNumpad(options = {}) {
	const numpadDisplay = ref("")

	const numpadValue = computed(() => {
		const val = Number.parseFloat(numpadDisplay.value)
		return Number.isNaN(val) ? 0 : val
	})

	/**
	 * Add a character to the numpad display
	 * @param {string} char - Character to add ('0'-'9', '.', '00')
	 */
	function numpadInput(char) {
		// Prevent multiple decimal points
		if (char === "." && numpadDisplay.value.includes(".")) {
			return
		}

		// Limit decimal places to 2
		if (numpadDisplay.value.includes(".")) {
			const [, decimal] = numpadDisplay.value.split(".")
			if (decimal && decimal.length >= 2) {
				return
			}
		}

		// Limit total length to reasonable amount
		if (numpadDisplay.value.length >= 10) {
			return
		}

		// Add the character
		numpadDisplay.value += char
	}

	/**
	 * Remove the last character from numpad display
	 */
	function numpadBackspace() {
		numpadDisplay.value = numpadDisplay.value.slice(0, -1)
	}

	/**
	 * Clear the numpad display
	 */
	function numpadClear() {
		numpadDisplay.value = ""
	}

	/**
	 * Set the numpad display to a specific value
	 * @param {number|string} value - Value to display
	 */
	function setNumpadValue(value) {
		if (typeof value === "number") {
			numpadDisplay.value = value.toFixed(2)
		} else {
			numpadDisplay.value = String(value)
		}
	}

	// Keyboard input handling
	const {
		isEnabled = ref(true),
		onEnter = null,
	} = options

	/**
	 * Handle keyboard input for physical keyboard support
	 * @param {KeyboardEvent} event
	 */
	function handleKeyboardInput(event) {
		// Check if keyboard input is enabled (e.g., dialog is open)
		const enabled = typeof isEnabled === 'function' ? isEnabled() : isEnabled.value
		if (!enabled) return

		// Don't handle if user is typing in an input field
		const activeElement = document.activeElement
		const isInInput = activeElement && (
			activeElement.tagName === 'INPUT' ||
			activeElement.tagName === 'TEXTAREA' ||
			activeElement.isContentEditable
		)
		if (isInInput) return

		const key = event.key

		// Handle numeric keys (0-9)
		if (/^[0-9]$/.test(key)) {
			event.preventDefault()
			numpadInput(key)
			return
		}

		// Handle decimal point (. or ,)
		if (key === '.' || key === ',') {
			event.preventDefault()
			numpadInput('.')
			return
		}

		// Handle backspace
		if (key === 'Backspace') {
			event.preventDefault()
			numpadBackspace()
			return
		}

		// Handle Delete or Escape to clear
		if (key === 'Delete' || key === 'Escape') {
			event.preventDefault()
			numpadClear()
			return
		}

		// Handle Enter - call custom handler if provided
		if (key === 'Enter') {
			event.preventDefault()
			if (onEnter && typeof onEnter === 'function') {
				onEnter(numpadValue.value)
			}
			return
		}
	}

	// Set up keyboard event listeners
	onMounted(() => {
		window.addEventListener('keydown', handleKeyboardInput)
	})

	onUnmounted(() => {
		window.removeEventListener('keydown', handleKeyboardInput)
	})

	return {
		// State
		numpadDisplay,
		numpadValue,

		// Actions
		numpadInput,
		numpadBackspace,
		numpadClear,
		setNumpadValue,
	}
}
