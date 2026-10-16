/**
 * Amount typed into a text input, shown with thousand separators as the rest
 * of the POS formats money (DEFAULT_LOCALE: "," groups, "." decimals).
 */

/** "15,000.5" -> 15000.5; anything unreadable -> 0 */
export function parseAmountInput(text) {
	const value = Number.parseFloat(String(text ?? "").replace(/,/g, ""));
	return Number.isFinite(value) ? value : 0;
}

/**
 * Re-format what the user typed, keeping a decimal part being typed:
 * "15000" -> "15,000", "1500.5" -> "1,500.5", "abc" -> "".
 */
export function formatAmountInput(text) {
	const clean = String(text ?? "").replace(/[^\d.]/g, "");
	if (!clean) return "";
	const [whole, ...rest] = clean.split(".");
	const grouped = (whole.replace(/^0+(?=\d)/, "") || "0").replace(/\B(?=(\d{3})+(?!\d))/g, ",");
	return rest.length ? `${grouped}.${rest.join("").slice(0, 2)}` : grouped;
}
