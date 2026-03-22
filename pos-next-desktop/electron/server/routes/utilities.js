/**
 * Utilities API - replaces pos_next.api.utilities
 * Static CSRF token for desktop mode (trusted local environment).
 */

async function getCsrfToken() {
	return "desktop-static-csrf-token"
}

module.exports = { getCsrfToken }
