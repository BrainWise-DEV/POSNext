/**
 * Currency formatting utility for POS Next
 * Provides consistent currency formatting across the application
 */

// Currency formatting constants
const DEFAULT_DECIMAL_PLACES = 2
const DEFAULT_LOCALE = "en-US"
const DEFAULT_CURRENCY = "USD"

// Currency symbol mapping for currencies without good Intl support
const CURRENCY_SYMBOLS = {
	EGP: "E£",
	SAR: "\u00EA",
	AED: "د.إ",
	INR: "₹",
	EUR: "€",
	GBP: "£",
	JPY: "¥",
	CNY: "¥",
	USD: "$",
}

/**
 * Get currency symbol for a specific currency code
 * @param {string} currency - The currency code
 * @returns {string} Currency symbol
 */
function getCurrencySymbolOnly(currency) {
	// Return mapped symbol or try to get from Intl
	if (CURRENCY_SYMBOLS[currency]) {
		return CURRENCY_SYMBOLS[currency]
	}

	// Fallback to Intl with narrowSymbol
	try {
		const parts = new Intl.NumberFormat(DEFAULT_LOCALE, {
			style: "currency",
			currency: currency,
			currencyDisplay: "narrowSymbol",
		}).formatToParts(0)
		const symbolPart = parts.find((part) => part.type === "currency")
		return symbolPart ? symbolPart.value : currency
	} catch {
		return currency
	}
}

/**
 * Format currency with proper locale and currency code
 * @param {number} value - The numeric value to format
 * @param {string} currency - The currency code (e.g., 'USD', 'EUR', 'EGP')
 * @param {string} locale - The locale for formatting (default: 'en-US' for English numbers)
 * @returns {string} Formatted currency string
 */
export function formatCurrency(value, currency = DEFAULT_CURRENCY, locale = DEFAULT_LOCALE) {
	if (typeof value !== "number" || isNaN(value)) {
		return ""
	}

	const absValue = Math.abs(value)
	const symbol = getCurrencySymbolOnly(currency)

	// Format number with locale
	const numberFormatted = new Intl.NumberFormat(locale, {
		minimumFractionDigits: DEFAULT_DECIMAL_PLACES,
		maximumFractionDigits: DEFAULT_DECIMAL_PLACES,
	}).format(absValue)

	// Combine symbol with formatted number (with space)
	const formatted = `${symbol} ${numberFormatted}`

	// Return with negative sign if needed
	return value < 0 ? `-${formatted}` : formatted
}

/**
 * Get currency symbol for a given currency code
 * @param {string} currency - The currency code (e.g., 'USD', 'EUR')
 * @returns {string} Currency symbol
 */
export function getCurrencySymbol(currency = DEFAULT_CURRENCY) {
	return getCurrencySymbolOnly(currency)
}

/**
 * Format currency without symbol (numbers only)
 * @param {number} value - The numeric value to format
 * @param {string} locale - The locale for formatting
 * @returns {string} Formatted number string
 */
export function formatCurrencyNumber(value, locale = DEFAULT_LOCALE) {
	if (typeof value !== "number" || isNaN(value)) {
		return "0.00"
	}

	return new Intl.NumberFormat(locale, {
		minimumFractionDigits: DEFAULT_DECIMAL_PLACES,
		maximumFractionDigits: DEFAULT_DECIMAL_PLACES,
	}).format(value)
}

/**
 * Get CSS class for currency values based on positive/negative
 * @param {number} value - The numeric value
 * @returns {string} CSS class string
 */
export function getCurrencyClass(value) {
	return value < 0 ? "text-red-600" : "text-gray-900"
}

/**
 * Round a number to 2 decimal places
 * Prevents floating point precision issues (e.g., 10.000000000000002)
 * @param {number} value - The numeric value to round
 * @returns {number} Rounded value
 */
export function round2(value) {
	if (typeof value !== "number" || isNaN(value)) {
		return 0
	}
	return Math.round(value * 100) / 100
}
