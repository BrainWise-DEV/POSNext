/**
 * Helpers for the customer email-verification fields
 * (custom_email_verified, custom_verified_email, custom_email_verified_on).
 */
import { call } from "frappe-ui";

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
