import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const callMock = vi.fn();
vi.mock("frappe-ui", () => ({ call: (...a) => callMock(...a) }));

import {
	applyVerificationPatch,
	canOfferEmailVerification,
	fetchFnfMembership,
	fetchVerificationStatus,
	STATUS_URL,
} from "../customerVerification";

describe("customerVerification", () => {
	beforeEach(() => callMock.mockReset());

	it("fetches fresh status and normalizes it", async () => {
		callMock.mockResolvedValue({
			custom_email_verified: 1,
			custom_verified_email: "a@b.com",
			custom_email_verified_on: "2026-10-18 10:00:00",
			custom_email_verified_by: "x",
		});
		const res = await fetchVerificationStatus("CUST-1");
		expect(callMock).toHaveBeenCalledWith(STATUS_URL, { customer: "CUST-1" });
		expect(res).toEqual({
			custom_email_verified: 1,
			custom_verified_email: "a@b.com",
			custom_email_verified_on: "2026-10-18 10:00:00",
		});
	});

	it("unwraps {message} and returns null on error", async () => {
		callMock.mockResolvedValueOnce({ message: { custom_email_verified: 1, custom_verified_email: "a@b.com" } });
		expect((await fetchVerificationStatus("C")).custom_email_verified).toBe(1);
		callMock.mockRejectedValueOnce(new Error("x"));
		expect(await fetchVerificationStatus("C")).toBeNull();
		expect(await fetchVerificationStatus("")).toBeNull();
	});

	it("patches only the matching customer (stale cart/edit objects regression)", () => {
		const stale = { name: "C1", custom_email_verified: 0, custom_verified_email: "" };
		const patch = { custom_email_verified: 1, custom_verified_email: "a@b.com" };
		const updated = applyVerificationPatch(stale, "C1", patch);
		expect(updated).toEqual({ name: "C1", ...patch });
		expect(updated).not.toBe(stale);
		const other = { name: "C2" };
		expect(applyVerificationPatch(other, "C1", patch)).toBe(other);
		expect(applyVerificationPatch(null, "C1", patch)).toBeNull();
		expect(applyVerificationPatch("C1", "C1", patch)).toBe("C1");
	});
});

describe("F&F membership (verification offered to F&F members)", () => {
	const ELIGIBILITY = "posnext_promotions.api.friends_and_family.check_friends_and_family_eligibility";
	beforeEach(() => {
		callMock.mockReset();
		vi.stubGlobal("window", { posnext_app_flags: { posnext_promotions: 1 } });
	});
	afterEach(() => vi.unstubAllGlobals());

	it("reads ff_member from the eligibility payload", async () => {
		callMock.mockResolvedValueOnce({ message: { eligible: false, reason: "email_not_verified", ff_member: true } });
		expect(await fetchFnfMembership("CUST-1", "P1")).toBe(true);
		expect(callMock).toHaveBeenCalledWith(ELIGIBILITY, { customer: "CUST-1", pos_profile: "P1" });
		callMock.mockResolvedValueOnce({ eligible: false, reason: "not_eligible", ff_member: false });
		expect(await fetchFnfMembership("CUST-2")).toBe(false);
		callMock.mockRejectedValueOnce(new Error("x"));
		expect(await fetchFnfMembership("CUST-3")).toBe(false);
	});

	it("is false without the Promotions app or a customer", async () => {
		vi.stubGlobal("window", { posnext_app_flags: {} });
		expect(await fetchFnfMembership("CUST-1")).toBe(false);
		expect(await fetchFnfMembership("")).toBe(false);
		expect(callMock).not.toHaveBeenCalled();
	});

	it("offers verification when the switch is on or the customer is an F&F member", () => {
		expect(canOfferEmailVerification({ switchEnabled: true, fnfMember: false })).toBe(true);
		expect(canOfferEmailVerification({ switchEnabled: false, fnfMember: true })).toBe(true);
		expect(canOfferEmailVerification({ switchEnabled: false, fnfMember: false })).toBe(false);
		expect(canOfferEmailVerification()).toBe(false);
	});
});
