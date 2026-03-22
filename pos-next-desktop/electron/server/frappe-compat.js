/**
 * Frappe API Compatibility Layer
 *
 * Makes Express responses match the exact contract that frappe-ui's call() expects:
 *   - Success: { message: <result> }
 *   - Error: { exc_type, _error_message, _server_messages }
 *
 * The frontend uses:
 *   POST /api/method/pos_next.api.<module>.<function>
 *   Body: JSON with function arguments
 *   Headers: X-Frappe-CSRF-Token (ignored locally)
 */

/**
 * Wrap an async handler to return Frappe-compatible JSON responses.
 * @param {Function} handler - async (params, req) => result
 * @returns {Function} Express route handler
 */
function frappeResponse(handler) {
	return async (req, res) => {
		try {
			const params = req.body || {}
			const result = await handler(params, req)
			res.json({ message: result })
		} catch (error) {
			const status = error.httpStatus || error.status || 500
			const excType = error.excType || error.name || "ServerError"
			const message = error.message || "Internal Server Error"

			console.error(`[API Error] ${excType}: ${message}`)

			res.status(status).json({
				exc_type: excType,
				_error_message: message,
				_server_messages: JSON.stringify([
					JSON.stringify({ message, indicator: "red" }),
				]),
			})
		}
	}
}

/**
 * Create a Frappe-style error for throwing in handlers.
 */
class FrappeError extends Error {
	constructor(message, { excType = "ValidationError", httpStatus = 417 } = {}) {
		super(message)
		this.name = excType
		this.excType = excType
		this.httpStatus = httpStatus
	}
}

/**
 * Authentication error (equivalent to frappe.AuthenticationError)
 */
class AuthenticationError extends FrappeError {
	constructor(message = "Authentication required") {
		super(message, { excType: "AuthenticationError", httpStatus: 401 })
	}
}

/**
 * Permission error (equivalent to frappe.PermissionError)
 */
class PermissionError extends FrappeError {
	constructor(message = "Insufficient permissions") {
		super(message, { excType: "PermissionError", httpStatus: 403 })
	}
}

/**
 * Register a route that maps a Frappe-style dotted path to an Express handler.
 * @param {express.Router} router - Express router
 * @param {string} method - Dotted method path (e.g. "pos_next.api.items.get_items")
 * @param {Function} handler - async (params, req) => result
 */
function registerMethod(router, method, handler) {
	router.post(`/api/method/${method}`, frappeResponse(handler))
}

module.exports = {
	frappeResponse,
	FrappeError,
	AuthenticationError,
	PermissionError,
	registerMethod,
}
