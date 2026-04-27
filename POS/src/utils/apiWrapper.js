import { call as frappeCall } from "frappe-ui"

import { forceRefreshCSRFToken, isCSRFApiError } from "./csrf"
import { desktopFrappeRequest } from "./desktopTransport"
import { runtimeConfig } from "./runtimeConfig"

/**
 * Frappe whitelisted-method invoker.
 *
 *  - Web mode: forwards to `frappe-ui`'s `call`, with CSRF auto-refresh on retry.
 *  - Desktop mode: routes through `desktopFrappeRequest` (Tauri Rust HTTP +
 *    `Authorization: token` header). CSRF doesn't apply.
 */
export async function call(method, params) {
	if (runtimeConfig.useRustTransport) {
		const path = method.startsWith("/") ? method : `/api/method/${method}`
		return desktopFrappeRequest({
			url: path,
			method: "POST",
			data: params || {},
		})
	}

	try {
		return await frappeCall(method, params)
	} catch (error) {
		if (isCSRFApiError(error)) {
			console.warn(
				"CSRF token error in call(), refreshing token and retrying...",
			)
			const refreshed = await forceRefreshCSRFToken()

			if (refreshed) {
				console.log("Retrying call after CSRF refresh...")
				return await frappeCall(method, params)
			}

			console.warn(
				"Could not refresh CSRF token. Server may have ignore_csrf enabled.",
			)
		}

		throw error
	}
}
