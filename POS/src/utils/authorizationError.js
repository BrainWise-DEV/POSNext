const AUTHORIZATION_TITLE = "Authorization Required";

/** Frappe's own wording when @rate_limit refuses a PIN submission (429). */
const RATE_LIMIT_PHRASE = "hit the rate limit";

/** Every string a Frappe error may carry its message in. */
function errorTexts(error) {
	if (!error || typeof error !== "object") return [];

	const parts = [];

	if (error._server_messages) {
		try {
			const parsed = JSON.parse(error._server_messages);
			for (const raw of Array.isArray(parsed) ? parsed : [parsed]) {
				parts.push(typeof raw === "string" ? raw : JSON.stringify(raw));
			}
		} catch {
			// Not JSON — fall back to the raw string.
			parts.push(String(error._server_messages));
		}
	}

	if (Array.isArray(error.messages)) parts.push(...error.messages.map(String));
	if (error.message) parts.push(String(error.message));
	if (typeof error.exc === "string") parts.push(error.exc);

	return parts;
}

/**
 * Whether a server error is the gate refusing an unauthorized action.
 * @param {unknown} error Error thrown by a resource submit.
 * @returns {boolean}
 */
export function isAuthorizationError(error) {
	return errorTexts(error).some((text) => text.includes(AUTHORIZATION_TITLE));
}

/**
 * @param {unknown} error Error thrown by requestGrant.
 * @returns {boolean}
 */
export function isRateLimitError(error) {
	if (error?.exc_type === "RateLimitExceededError") return true;
	if (Number(error?.httpStatus ?? error?.status) === 429) return true;
	return errorTexts(error).some((text) => text.includes(RATE_LIMIT_PHRASE));
}
