/**
 * Whether the POS may log in here. Browsers hide Web Crypto (needed for the offline
 * unlock hash) outside secure contexts, and a till must not send passwords over plain
 * http; plain http is allowed only in frontend (Vite) or backend (developer_mode) dev mode.
 *
 * @param {{ isSecureContext?: boolean, frontendDev?: boolean, backendDev?: boolean|number }} env
 * @returns {boolean}
 */
export function canLogin({ isSecureContext = false, frontendDev = false, backendDev = false } = {}) {
	return Boolean(isSecureContext || frontendDev || backendDev);
}

/** The current page's environment for canLogin(). */
export function currentLoginEnv() {
	return {
		isSecureContext: window.isSecureContext,
		frontendDev: import.meta.env.DEV,
		backendDev: window.posnext_developer_mode,
	};
}
