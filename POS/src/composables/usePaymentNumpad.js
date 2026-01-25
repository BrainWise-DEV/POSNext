/**
 * Payment Numpad Composable
 * Handles numeric keypad state and input for payment dialog
 */

import { ref, computed } from "vue"

export function usePaymentNumpad() {
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
