/**
 * Currency Utility for POS Next
 * Handles formatting and rounding with ERPNext System Settings compatibility
 *
 * Rounding Methods (matches frappe/utils/data.py):
 * - Banker's Rounding: Rounds .5 to nearest even number
 * - Commercial Rounding: Rounds .5 away from zero
 */

// =============================================================================
// Settings (initialized from bootstrap)
// =============================================================================

let settings = {
	currency: 2,
	float: 3,
	rounding_method: "Banker's Rounding",
	number_format: "#,###.##",
}

/** Initialize settings from bootstrap data */
export function initPrecision(data) {
	if (!data) return
	settings = {
		currency: data.currency ?? 2,
		float: data.float ?? 3,
		rounding_method: data.rounding_method || "Banker's Rounding",
		number_format: data.number_format || "#,###.##",
	}
	_formatterCache.clear()
}

/** Get current settings */
export function getPrecision() {
	return { ...settings }
}

// =============================================================================
// Currency Symbols
// =============================================================================

export const DEFAULT_CURRENCY = "USD"
export const DEFAULT_LOCALE = "en-US"

const SYMBOLS = {
	USD: "$",
	EUR: "€",
	GBP: "£",
	JPY: "¥",
	CNY: "¥",
	INR: "₹",
	EGP: "E£",
	SAR: "\u00EA",
	AED: "د.إ",
}

const _symbolCache = new Map()

function getSymbol(currency) {
	if (!currency) return SYMBOLS[DEFAULT_CURRENCY]
	if (SYMBOLS[currency]) return SYMBOLS[currency]
	if (_symbolCache.has(currency)) return _symbolCache.get(currency)

	try {
		const parts = new Intl.NumberFormat(DEFAULT_LOCALE, {
			style: "currency",
			currency,
			currencyDisplay: "narrowSymbol",
		}).formatToParts(0)
		const symbol = parts.find((p) => p.type === "currency")?.value || currency
		_symbolCache.set(currency, symbol)
		return symbol
	} catch {
		_symbolCache.set(currency, currency)
		return currency
	}
}

export { getSymbol as getCurrencySymbol }

// =============================================================================
// Number Formatting
// =============================================================================

const _formatterCache = new Map()

function getFormatter(precision, locale = DEFAULT_LOCALE) {
	const key = `${locale}:${precision}`
	if (!_formatterCache.has(key)) {
		_formatterCache.set(
			key,
			new Intl.NumberFormat(locale, {
				minimumFractionDigits: precision,
				maximumFractionDigits: precision,
			}),
		)
	}
	return _formatterCache.get(key)
}

/** Format value as currency string with symbol */
export function formatCurrency(value, currency = DEFAULT_CURRENCY, locale = DEFAULT_LOCALE) {
	if (typeof value !== "number" || Number.isNaN(value)) return ""
	const abs = Math.abs(value)
	const formatted = `${getSymbol(currency)} ${getFormatter(settings.currency, locale).format(abs)}`
	return value < 0 ? `-${formatted}` : formatted
}

/** Format value as number string (no symbol) */
export function formatCurrencyNumber(value, locale = DEFAULT_LOCALE) {
	if (typeof value !== "number" || Number.isNaN(value)) return "0.00"
	return getFormatter(settings.currency, locale).format(value)
}

/** Get CSS class for positive/negative values */
export function getCurrencyClass(value) {
	return value < 0 ? "text-red-600" : "text-gray-900"
}

// =============================================================================
// Rounding (matches frappe/utils/data.py exactly)
// =============================================================================

/**
 * Banker's Rounding - rounds .5 to nearest even
 * Matches frappe _bankers_rounding()
 */
function bankersRound(num, precision) {
	const multiplier = 10 ** precision
	// Round to 12 decimal places first to handle floating point errors
	let shifted = Number((num * multiplier).toFixed(12))

	if (shifted === 0) return 0

	const floor = Math.floor(shifted)
	const decimal = shifted - floor

	// Calculate epsilon for this number's magnitude
	const epsilon = 2 ** (Math.log2(Math.abs(shifted)) - 52)

	if (Math.abs(decimal - 0.5) < epsilon) {
		// Exactly .5 - round to even
		shifted = floor % 2 === 0 ? floor : floor + 1
	} else {
		shifted = Math.round(shifted)
	}

	return shifted / multiplier
}

/**
 * Commercial Rounding - .5 rounds away from zero
 * Matches frappe _round_away_from_zero()
 */
function commercialRound(num, precision) {
	if (num === 0) return 0

	// Calculate epsilon for this number's magnitude
	const epsilon = 2 ** (Math.log2(Math.abs(num)) - 52)

	// Add epsilon in the direction of the sign, then round
	const adjusted = num + Math.sign(num) * epsilon
	return Number(adjusted.toFixed(precision))
}

/**
 * Round using system rounding method
 * @param {number} value - Value to round
 * @param {number} precision - Decimal places
 * @returns {number} Rounded value
 */
function round(value, precision) {
	if (typeof value !== "number" || Number.isNaN(value)) return 0

	// Use Frappe's flt() if available in browser context
	if (typeof window !== "undefined" && typeof window.flt === "function") {
		return window.flt(value, precision)
	}

	// Apply rounding based on system setting
	if (settings.rounding_method === "Commercial Rounding") {
		return commercialRound(value, precision)
	}
	return bankersRound(value, precision)
}

// =============================================================================
// Exported Rounding Functions
// =============================================================================

/** Round to 2 decimal places */
export function round2(value) {
	return round(value, 2)
}

/** Round to 3 decimal places */
export function round3(value) {
	return round(value, 3)
}

/** Round using system currency precision */
export function roundCurrency(value) {
	return round(value, settings.currency)
}

/** Round using system float precision */
export function roundFloat(value) {
	return round(value, settings.float)
}
