/**
 * runtimeConfig — single source of truth for "where do we run, and against what backend".
 *
 * The Vue app ships in two modes:
 *  - "web"     (default): served by Frappe at /pos. Same-origin. Cookie + CSRF auth.
 *                         API base URL is "" (relative paths). Socket.IO active.
 *  - "desktop"           : packaged in Tauri. Runs from a tauri:// origin and talks to
 *                          a remote Frappe Cloud site over HTTPS via Tauri's Rust HTTP
 *                          plugin. API key/secret auth, no cookies, no CSRF, no SW,
 *                          no Socket.IO.
 *
 * Vite injects __POS_TARGET__ and __FRAPPE_BASE_URL__ at build time (see vite.config.js).
 * Both fall back to safe web-mode defaults so this module imports cleanly under Vitest
 * and during the existing browser build.
 */

const TARGET =
	(typeof __POS_TARGET__ !== "undefined" ? __POS_TARGET__ : "web") || "web"
const BASE_URL =
	(typeof __FRAPPE_BASE_URL__ !== "undefined" ? __FRAPPE_BASE_URL__ : "") || ""

const isDesktop = TARGET === "desktop"

function trimSlash(url) {
	if (!url) return ""
	return url.endsWith("/") ? url.slice(0, -1) : url
}

const baseUrl = trimSlash(BASE_URL)

let cachedAuthHeader = null

/**
 * Build a fully-qualified URL from a Frappe path.
 *  - In web mode, paths stay relative ("/api/method/foo").
 *  - In desktop mode, paths get the Frappe Cloud origin prepended.
 *
 * @param {string} path - e.g. "/api/method/pos_next.api.ping"
 * @returns {string}
 */
export function apiUrl(path) {
	if (!path) return baseUrl || ""
	if (/^https?:\/\//i.test(path)) return path
	const normalized = path.startsWith("/") ? path : `/${path}`
	return `${baseUrl}${normalized}`
}

/**
 * Set the API key/secret pair to use for desktop auth. Persisted by the caller
 * (typically the Login flow into Stronghold); this module just keeps it in
 * memory for fast access from request wrappers.
 */
export function setApiCredentials({ apiKey, apiSecret } = {}) {
	if (apiKey && apiSecret) {
		cachedAuthHeader = `token ${apiKey}:${apiSecret}`
	} else {
		cachedAuthHeader = null
	}
}

/** Read the cached Authorization header value, or null if unset. */
export function getAuthHeader() {
	return cachedAuthHeader
}

/** Clear the in-memory credentials. Stronghold wipe is the caller's job. */
export function clearApiCredentials() {
	cachedAuthHeader = null
}

export const runtimeConfig = Object.freeze({
	target: TARGET,
	isDesktop,
	isWeb: !isDesktop,
	baseUrl,
	useRustTransport: isDesktop,
	hasRealtime: !isDesktop,
	hasServiceWorker: !isDesktop,
})

export default runtimeConfig
