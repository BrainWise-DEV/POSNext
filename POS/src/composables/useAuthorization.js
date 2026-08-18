import { promoApi } from "@/utils/promoApi";
import { call } from "@/utils/apiWrapper";
import { useBootstrapStore } from "@/stores/bootstrap";
import { logger } from "@/utils/logger";
import { reactive } from "vue";

const log = logger.create("Authorization");

const state = reactive({
	open: false,
	action: null,
	actionLabel: "",
	context: null,
	resolve: null,
});

function settle(grant) {
	const resolve = state.resolve;
	state.open = false;
	state.action = null;
	state.actionLabel = "";
	state.context = null;
	state.resolve = null;
	if (resolve) resolve(grant);
}

export function useAuthorization() {
	/**
	 * Whether an action is gated on this POS Profile, per the bootstrap payload.
	 * @param {string} action
	 * @returns {boolean}
	 */
	function isAuthorizationRequired(action) {
		const bootstrap = useBootstrapStore();
		const policy = bootstrap.data?.authorization_policy || {};
		return Boolean(policy[action]);
	}

	/**
	 * Ask for approval, if this action needs it.
	 *
	 * @param {string} action Registered action name, e.g. "Sales Invoice Return" — this
	 *   is both the registry key and its display text (see pos_next.authorization.registry),
	 *   so it must be the human-readable string, not a snake_case code.
	 * @param {object} context Passed to the server to bind the grant. Include every value
	 *   the action's binding uses — for returns that is pos_profile, return_against or
	 *   customer, and amount.
	 * @returns {Promise<object|null>} The grant, or null when the user cancelled.
	 *   Returns a stub grant with no token when the action is not gated, so callers can
	 *   treat "not required" and "approved" the same way.
	 */
	async function requireAuthorization(action, context = {}) {
		if (!isAuthorizationRequired(action)) {
			return { grant_token: null, required: false };
		}

		return new Promise((resolve) => {
			state.action = action;
			state.actionLabel = context.actionLabel || "";
			state.context = context;
			state.resolve = resolve;
			state.open = true;
		});
	}

	return { requireAuthorization, isAuthorizationRequired };
}

/**
 * Internal wiring for <AuthorizationDialog />. Not for general use.
 */
export function useAuthorizationDialog() {
	async function loadAuthorizers() {
		try {
			return await call(promoApi.getAuthorizers(), {
				action: state.action,
				pos_profile: state.context?.pos_profile,
				context: JSON.stringify(state.context || {}),
			});
		} catch (error) {
			log.error("Failed to load authorizers", error);
			return [];
		}
	}

	async function requestGrant(approver, pin) {
		return await call(promoApi.requestGrant(), {
			action: state.action,
			approver,
			pin,
			context: JSON.stringify(state.context || {}),
		});
	}

	/**
	 * Digits the PIN input should accept, set server-side by POS Authorization
	 */
	function pinLength() {
		const bootstrap = useBootstrapStore();
		return Number(bootstrap.data?.authorization_pin_length) || 4;
	}

	return {
		state,
		loadAuthorizers,
		requestGrant,
		pinLength,
		approve: (grant) => settle(grant),
		cancel: () => settle(null),
	};
}
