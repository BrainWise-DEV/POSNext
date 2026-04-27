/**
 * desktopTransport — Tauri-aware HTTP transport for Frappe API calls.
 *
 * In desktop mode, all requests route through `@tauri-apps/plugin-http`'s `fetch`,
 * which makes the actual network call from Rust. That bypasses the WebView's CORS
 * (no preflights, no Access-Control-* headers needed on Frappe Cloud) and lets us
 * authenticate with `Authorization: token <key>:<secret>` instead of session cookies.
 *
 * This module mirrors the shape of `frappe-ui`'s `frappeRequest` so it can be slotted
 * straight into `setConfig("resourceFetcher", …)`. It also exposes `tauriFetch`
 * for code that needs raw fetch semantics (e.g. the login flow).
 */

import { apiUrl, getAuthHeader, runtimeConfig } from "./runtimeConfig"

let _fetchImpl = null

async function loadTauriFetch() {
	if (_fetchImpl) return _fetchImpl
	const mod = await import("@tauri-apps/plugin-http")
	_fetchImpl = mod.fetch
	return _fetchImpl
}

function buildHeaders(extra = {}) {
	const headers = {
		Accept: "application/json",
		"X-Frappe-Site-Name": new URL(runtimeConfig.baseUrl).hostname,
		...extra,
	}
	const auth = getAuthHeader()
	if (auth) headers.Authorization = auth
	return headers
}

/**
 * Raw fetch against the configured Frappe Cloud origin via Tauri's HTTP plugin.
 *
 * @param {string} path - "/api/method/..." or absolute URL
 * @param {RequestInit} [init]
 * @returns {Promise<Response>}
 */
export async function tauriFetch(path, init = {}) {
	const fetchFn = await loadTauriFetch()
	const url = apiUrl(path)
	const merged = {
		...init,
		headers: buildHeaders(init.headers),
	}
	return fetchFn(url, merged)
}

function isFormDataLike(value) {
	return (
		typeof FormData !== "undefined" &&
		(value instanceof FormData ||
			(value &&
				typeof value === "object" &&
				value.constructor?.name === "FormData"))
	)
}

function encodeBody(body, headers) {
	if (body == null) return undefined
	if (typeof body === "string") return body
	if (isFormDataLike(body)) return body
	headers["Content-Type"] = headers["Content-Type"] || "application/json"
	return JSON.stringify(body)
}

/**
 * `frappe-ui`-shaped resource fetcher. Accepts a single options object the way
 * `frappeRequest` does and returns the unwrapped `message` payload (or throws).
 */
export async function desktopFrappeRequest(options = {}) {
	const {
		url,
		method = "GET",
		params,
		data,
		headers: extraHeaders = {},
		auth,
		onSuccess,
		onError,
	} = options

	if (!url) throw new Error("desktopFrappeRequest: missing url")

	const upperMethod = String(method).toUpperCase()
	const headers = buildHeaders(extraHeaders)

	let target = url
	if (params && typeof params === "object" && upperMethod === "GET") {
		const usp = new URLSearchParams()
		for (const [k, v] of Object.entries(params)) {
			if (v == null) continue
			usp.append(k, typeof v === "object" ? JSON.stringify(v) : String(v))
		}
		const qs = usp.toString()
		if (qs) target += target.includes("?") ? `&${qs}` : `?${qs}`
	}

	const body =
		upperMethod === "GET" || upperMethod === "HEAD"
			? undefined
			: encodeBody(data ?? params, headers)

	const fetchFn = await loadTauriFetch()
	const response = await fetchFn(apiUrl(target), {
		method: upperMethod,
		headers,
		body,
	})

	const contentType = response.headers.get("content-type") || ""
	let payload = null
	if (contentType.includes("application/json")) {
		try {
			payload = await response.json()
		} catch {
			payload = null
		}
	} else {
		try {
			payload = await response.text()
		} catch {
			payload = null
		}
	}

	if (!response.ok) {
		const error = new Error(
			(payload &&
				(payload.exception || payload._server_messages || payload.message)) ||
				`HTTP ${response.status}`,
		)
		error.status = response.status
		error.response = response
		error.payload = payload
		if (typeof onError === "function") {
			try {
				onError(error)
			} catch {
				/* swallow */
			}
		}
		throw error
	}

	const result =
		payload && Object.prototype.hasOwnProperty.call(payload, "message")
			? payload.message
			: payload

	if (typeof onSuccess === "function") {
		try {
			onSuccess(result)
		} catch {
			/* swallow */
		}
	}

	return result
}

export default desktopFrappeRequest
