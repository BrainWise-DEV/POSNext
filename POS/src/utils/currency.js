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
};

/** Initialize settings from bootstrap data */
export function initPrecision(data) {
	if (!data) return;
	settings = {
		currency: data.currency ?? 2,
		float: data.float ?? 3,
		rounding_method: data.rounding_method || "Banker's Rounding",
		number_format: data.number_format || "#,###.##",
	};
	_formatterCache.clear();
}

/** Get current settings */
export function getPrecision() {
	return { ...settings };
}

// =============================================================================
// Currency Symbols
// =============================================================================

export const DEFAULT_CURRENCY = "USD";
const FALLBACK_LOCALE = "en-US";

/** BCP 47 locale for a language code, with Latin digits (e.g. "ar" → "ar-EG-u-nu-latn") */
function toLocale(lang) {
	const tag = { ar: "ar-EG", en: "en-US" }[lang?.toLowerCase()] || lang;
	try {
		return tag ? Intl.getCanonicalLocales(`${tag}-u-nu-latn`)[0] : FALLBACK_LOCALE;
	} catch {
		return FALLBACK_LOCALE;
	}
}

/** User's locale from boot/session, falling back to en-US; updated by setLocale() */
export let DEFAULT_LOCALE = toLocale(
	globalThis.frappe?.boot?.lang || globalThis.localStorage?.getItem("pos_next_language")
);

/** Switch formatting to the given language code (null resets to en-US) */
export function setLocale(lang) {
	DEFAULT_LOCALE = toLocale(lang);
	_formatterCache.clear();
}

const isArabic = (locale) => locale.startsWith("ar");

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
};

const _symbolCache = new Map();

function getSymbol(currency, locale = DEFAULT_LOCALE) {
	if (!currency) return SYMBOLS[DEFAULT_CURRENCY];
	if (currency === "EGP" && isArabic(locale)) return "ج.م";
	if (SYMBOLS[currency]) return SYMBOLS[currency];
	const key = `${locale}:${currency}`;
	if (_symbolCache.has(key)) return _symbolCache.get(key);

	try {
		const parts = new Intl.NumberFormat(locale, {
			style: "currency",
			currency,
			currencyDisplay: "narrowSymbol",
		}).formatToParts(0);
		const symbol = parts.find((p) => p.type === "currency")?.value || currency;
		_symbolCache.set(key, symbol);
		return symbol;
	} catch {
		_symbolCache.set(key, currency);
		return currency;
	}
}

export { getSymbol as getCurrencySymbol };

// =============================================================================
// Number Formatting
// =============================================================================

const _formatterCache = new Map();

function getFormatter(precision, locale = DEFAULT_LOCALE) {
	const key = `${locale}:${precision}`;
	if (!_formatterCache.has(key)) {
		_formatterCache.set(
			key,
			new Intl.NumberFormat(locale, {
				minimumFractionDigits: precision,
				maximumFractionDigits: precision,
			})
		);
	}
	return _formatterCache.get(key);
}

/** Format value as currency string with symbol (after the amount in Arabic: "1,234.50 ج.م") */
export function formatCurrency(value, currency = DEFAULT_CURRENCY, locale = DEFAULT_LOCALE) {
	if (typeof value !== "number" || Number.isNaN(value)) return "";
	const abs = Math.abs(value);
	const number = getFormatter(settings.currency, locale).format(abs);
	// LTR isolate keeps the minus sign left of the digits in RTL text
	if (isArabic(locale)) {
		return `${value < 0 ? `\u2066-${number}\u2069` : number} ${getSymbol(currency, locale)}`;
	}
	const formatted = `${getSymbol(currency, locale)} ${number}`;
	return value < 0 ? `-${formatted}` : formatted;
}

/** Format value as number string (no symbol) */
export function formatCurrencyNumber(value, locale = DEFAULT_LOCALE) {
	if (typeof value !== "number" || Number.isNaN(value)) return "0.00";
	return getFormatter(settings.currency, locale).format(value);
}

// =============================================================================
// Date Formatting
// =============================================================================

const DATE_OPTIONS = { day: "numeric", month: "short", year: "numeric" };
const TIME_OPTIONS = { hour: "numeric", minute: "2-digit", hour12: true };

/** Parse a Date, timestamp, "YYYY-MM-DD" (local day), "HH:MM[:SS]" or Frappe datetime string */
function toDate(value) {
	const ymd = typeof value === "string" && value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
	const hms = typeof value === "string" && value.match(/^(\d{1,2}):(\d{2})/);
	const date = ymd
		? new Date(ymd[1], ymd[2] - 1, ymd[3])
		: hms
			? new Date(1970, 0, 1, hms[1], hms[2])
			: new Date(typeof value === "string" ? value.replace(" ", "T") : value);
	return Number.isNaN(date.getTime()) ? null : date;
}

/** Format date with month name: "5 نوفمبر 2026" / "Nov 5, 2026" */
export function formatDate(value, locale = DEFAULT_LOCALE) {
	const date = value ? toDate(value) : null;
	return date ? date.toLocaleDateString(locale, DATE_OPTIONS) : "";
}

/** Format 12h time: "9:15 م" / "9:15 PM" */
export function formatTime(value, locale = DEFAULT_LOCALE) {
	const date = value ? toDate(value) : null;
	return date ? date.toLocaleTimeString(locale, TIME_OPTIONS) : "";
}

/** Format date and 12h time: "5 نوفمبر 2026، 9:15 م" / "Nov 5, 2026, 9:15 PM" */
export function formatDateTime(value, locale = DEFAULT_LOCALE) {
	const date = value ? toDate(value) : null;
	return date ? date.toLocaleString(locale, { ...DATE_OPTIONS, ...TIME_OPTIONS }) : "";
}

/** Get CSS class for positive/negative values */
export function getCurrencyClass(value) {
	return value < 0 ? "text-red-600" : "text-gray-900";
}

// =============================================================================
// Rounding (matches frappe/utils/data.py exactly)
// =============================================================================

/**
 * Banker's Rounding - rounds .5 to nearest even
 * Matches frappe _bankers_rounding()
 */
function bankersRound(num, precision) {
	const multiplier = 10 ** precision;
	// Round to 12 decimal places first to handle floating point errors
	let shifted = Number((num * multiplier).toFixed(12));

	if (shifted === 0) return 0;

	const floor = Math.floor(shifted);
	const decimal = shifted - floor;

	// Calculate epsilon for this number's magnitude
	const epsilon = 2 ** (Math.log2(Math.abs(shifted)) - 52);

	if (Math.abs(decimal - 0.5) < epsilon) {
		// Exactly .5 - round to even
		shifted = floor % 2 === 0 ? floor : floor + 1;
	} else {
		shifted = Math.round(shifted);
	}

	return shifted / multiplier;
}

/**
 * Commercial Rounding - .5 rounds away from zero
 * Matches frappe _round_away_from_zero()
 */
function commercialRound(num, precision) {
	if (num === 0) return 0;

	// Calculate epsilon for this number's magnitude
	const epsilon = 2 ** (Math.log2(Math.abs(num)) - 52);

	// Add epsilon in the direction of the sign, then round
	const adjusted = num + Math.sign(num) * epsilon;
	return Number(adjusted.toFixed(precision));
}

/**
 * Round using system rounding method
 * @param {number} value - Value to round
 * @param {number} precision - Decimal places
 * @returns {number} Rounded value
 */
function round(value, precision) {
	if (typeof value !== "number" || Number.isNaN(value)) return 0;

	// Use Frappe's flt() if available in browser context
	if (typeof window !== "undefined" && typeof window.flt === "function") {
		return window.flt(value, precision);
	}

	// Apply rounding based on system setting
	if (settings.rounding_method === "Commercial Rounding") {
		return commercialRound(value, precision);
	}
	return bankersRound(value, precision);
}

// =============================================================================
// Exported Rounding Functions
// =============================================================================

/** Round to 2 decimal places */
export function round2(value) {
	return round(value, 2);
}

/** Round to 3 decimal places */
export function round3(value) {
	return round(value, 3);
}

/** Round using system currency precision */
export function roundCurrency(value) {
	return round(value, settings.currency);
}

/** Round using system float precision */
export function roundFloat(value) {
	return round(value, settings.float);
}
