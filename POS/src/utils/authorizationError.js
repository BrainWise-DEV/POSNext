const AUTHORIZATION_TITLE = "Authorization Required";

/**
 * Whether a server error is the gate refusing an unauthorized action.
 * @param {unknown} error Error thrown by a resource submit.
 * @returns {boolean}
 */
export function isAuthorizationError(error) {
	if (!error || typeof error !== "object") return false;

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

	return parts.some((text) => text.includes(AUTHORIZATION_TITLE));
}
