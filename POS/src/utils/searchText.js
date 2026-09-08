/**
 * Arabic-aware text normalization and match segmentation for instant search.
 *
 * Normalization makes search forgiving for Arabic input:
 * - strips diacritics (تشكيل)
 * - unifies alef variants (أ إ آ ٱ → ا), ة → ه, ى → ي, ؤ → و, ئ → ي
 * - converts Arabic-Indic digits (٠-٩, ۰-۹) to Latin digits
 * - lowercases Latin text
 */

const ARABIC_DIACRITICS =
	/[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06dc\u06df-\u06e4\u06e7\u06e8\u06ea-\u06ed]/g

/**
 * Normalize a string for matching. Safe on empty/nullish input.
 * @param {String} text
 * @returns {String} normalized text
 */
export function normalizeSearchText(text) {
	if (!text) return ""
	return String(text)
		.toLowerCase()
		.replace(ARABIC_DIACRITICS, "")
		.replace(/[أإآٱ]/g, "ا")
		.replace(/ة/g, "ه")
		.replace(/ى/g, "ي")
		.replace(/ؤ/g, "و")
		.replace(/ئ/g, "ي")
		.replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660))
		.replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
}

/**
 * Split a raw query into normalized tokens.
 * @param {String} query
 * @returns {String[]} non-empty normalized tokens
 */
export function tokenizeQuery(query) {
	return normalizeSearchText(query).split(/\s+/).filter(Boolean)
}

/**
 * Normalize a string while keeping a map from each normalized character
 * back to its index in the original string (diacritics are dropped, so the
 * mapping is not 1:1).
 */
function normalizeWithMap(text) {
	const chars = []
	const map = []
	for (let i = 0; i < text.length; i++) {
		const n = normalizeSearchText(text[i])
		for (const c of n) {
			chars.push(c)
			map.push(i)
		}
	}
	return { norm: chars.join(""), map }
}

/**
 * Split text into segments marking the parts matched by the tokens, for
 * rendering highlighted search results. Matching is normalization-aware,
 * so typing "أحمد" highlights "احمد" and vice versa.
 *
 * @param {String} text - original display text
 * @param {String[]} tokens - normalized tokens (from tokenizeQuery)
 * @returns {Array<{text: String, hit: Boolean}>} ordered segments
 */
export function matchSegments(text, tokens) {
	if (!text) return []
	if (!tokens || tokens.length === 0) return [{ text, hit: false }]

	const { norm, map } = normalizeWithMap(text)
	const hits = new Array(text.length).fill(false)
	for (const token of tokens) {
		let from = 0
		// Mark every occurrence so repeated fragments all light up
		for (;;) {
			const idx = norm.indexOf(token, from)
			if (idx === -1) break
			const start = map[idx]
			const end = map[idx + token.length - 1]
			for (let i = start; i <= end; i++) hits[i] = true
			from = idx + token.length
		}
	}

	const segments = []
	for (let i = 0; i < text.length; i++) {
		const last = segments[segments.length - 1]
		if (last && last.hit === hits[i]) {
			last.text += text[i]
		} else {
			segments.push({ text: text[i], hit: hits[i] })
		}
	}
	return segments
}
