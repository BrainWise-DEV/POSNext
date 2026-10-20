/**
 * Helpers for the customer email-verification fields
 * (custom_email_verified, custom_verified_email, custom_email_verified_on).
 */
import { call } from "frappe-ui";
import { promoApi } from "@/utils/promoApi";

export const STATUS_URL = "pos_next.api.email_verification.get_email_verification_status";

/** Fetch the authoritative verification flags from the server (null on failure). */
export async function fetchVerificationStatus(customer) {
	if (!customer) return null;
	try {
		const res = await call(STATUS_URL, { customer });
		const data = res?.message && typeof res.message === "object" ? res.message : res;
		if (!data || typeof data !== "object") return null;
		return {
			custom_email_verified: Number(data.custom_email_verified) ? 1 : 0,
			custom_verified_email: data.custom_verified_email || "",
			custom_email_verified_on: data.custom_email_verified_on || "",
		};
	} catch {
		return null;
	}
}

/** Return `customer` merged with `patch` when it is the same customer, else unchanged. */
export function applyVerificationPatch(customer, name, patch) {
	if (!customer || typeof customer !== "object" || customer.name !== name) return customer;
	return { ...customer, ...patch };
}

/**
 * Whether the customer is a Friends & Family member (POSNext Promotions). F&F
 * requires a verified email, so members can be verified even when the general
 * POS email-verification switch is off. False when the app is absent / on error.
 */
export async function fetchFnfMembership(customer, posProfile = null) {
	const method = promoApi.checkFriendsAndFamilyEligibility();
	if (!customer || !method) return false;
	try {
		const res = await call(method, { customer, pos_profile: posProfile || undefined });
		const data = res?.message && typeof res.message === "object" ? res.message : res;
		return Boolean(data?.ff_member);
	} catch {
		return false;
	}
}

/** Show the email-verification UI: POS switch on, or the customer is an F&F member. */
export function canOfferEmailVerification({ switchEnabled = false, fnfMember = false } = {}) {
	return Boolean(switchEnabled || fnfMember);
}
