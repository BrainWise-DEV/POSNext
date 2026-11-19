/**
 * useFormatters composable
 * Provides common formatting functions for use across all components
 */
import {
	formatDate as formatLocaleDate,
	formatDateTime as formatLocaleDateTime,
	formatTime as formatLocaleTime,
} from "@/utils/currency";

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
 * Format date and time in the user's locale
 * @param {string|Date} datetime - The datetime to format
 * @returns {string} Formatted date and time string (e.g. "Nov 5, 2026, 9:15 PM")
 */
function formatDateTime(datetime) {
	return formatLocaleDateTime(datetime);
}

/**
 * Format time to HH:MM AM/PM only (hours and minutes)
 * Handles both Date objects and time strings (e.g., "15:31:22.975239")
 * @param {string|Date} time - The time to format
 * @returns {string} Formatted time string (e.g. "9:15 PM", "9:15 م")
 */
function formatTime(time) {
	return formatLocaleTime(time);
}

/**
 * Format date only, with month name (e.g. "Nov 5, 2026", "5 نوفمبر 2026")
 * @param {string|Date} date - The date to format
 * @returns {string} Formatted date string
 */
function formatDate(date) {
	return formatLocaleDate(date);
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
