/**
 * useFormatters composable
 * Provides common formatting functions for use across all components
 */

/**
 * Format currency values to 2 decimal places
 * @param {number} amount - The amount to format
 * @returns {string} Formatted amount with 2 decimal places
 */
function formatCurrency(amount) {
	if (amount === null || amount === undefined) return "0.00";
	return Number.parseFloat(amount).toFixed(2);
}

/**
 * Format quantity values with smart decimal handling
 * Rounds to 4 decimal places and removes trailing zeros
 * @param {number} quantity - The quantity to format
 * @returns {string} Formatted quantity
 */
function formatQuantity(quantity) {
	if (quantity === null || quantity === undefined) return "0";
	const num = Number.parseFloat(quantity);
	if (Number.isNaN(num)) return "0";
	// Round to 4 decimal places and remove trailing zeros
	return num.toFixed(4).replace(/\.?0+$/, "");
}

/**
 * Format date and time
 * @param {string|Date} datetime - The datetime to format
 * @returns {string} Formatted date and time string
 */
function formatDateTime(datetime) {
	if (!datetime) return "";
	return new Date(datetime).toLocaleString();
}

/**
 * Format time to HH:MM AM/PM only (hours and minutes)
 * Handles both Date objects and time strings (e.g., "15:31:22.975239")
 * @param {string|Date} time - The time to format
 * @returns {string} Formatted time string (HH:MM AM/PM)
 */
function formatTime(time) {
	if (!time) return "";

	// If it's a time string (contains colon), extract HH:MM
	if (typeof time === "string" && time.includes(":")) {
		const parts = time.split(":");
		if (parts.length >= 2) {
			const hours = Number.parseInt(parts[0], 10);
			const minutes = parts[1];
			if (Number.isNaN(hours)) return time;

			const period = hours >= 12 ? "PM" : "AM";
			const displayHours = hours % 12 || 12;
			return `${displayHours}:${minutes} ${period}`;
		}
		return time;
	}

	// If it's a Date object or datetime string, convert and format
	return new Date(time).toLocaleTimeString([], {
		hour: "numeric",
		minute: "2-digit",
		hour12: true,
	});
}

/**
 * Format date only (short format: DD/MM/YY)
 * @param {string|Date} date - The date to format
 * @returns {string} Formatted date string
 */
function formatDate(date) {
	if (!date) return "";

	if (typeof date === "string") {
		const match = date.match(/^(\d{4})-(\d{2})-(\d{2})$/);
		if (match) {
			const [, year, month, day] = match;
			return `${day}/${month}/${year.slice(-2)}`;
		}
	}

	return new Date(date).toLocaleDateString("en-GB", {
		day: "2-digit",
		month: "2-digit",
		year: "2-digit",
	});
}

/**
 * Format percentage values
 * @param {number} value - The value to format as percentage
 * @param {number} decimals - Number of decimal places (default: 2)
 * @returns {string} Formatted percentage
 */
function formatPercentage(value, decimals = 2) {
	if (value === null || value === undefined) return "0%";
	return `${Number.parseFloat(value)
		.toFixed(decimals)
		.replace(/\.?0+$/, "")}%`;
}

/**
 * Composable function to use formatters
 * @returns {Object} Object containing all formatter functions
 */
export function useFormatters() {
	return {
		formatCurrency,
		formatQuantity,
		formatDateTime,
		formatTime,
		formatDate,
		formatPercentage,
	};
}
