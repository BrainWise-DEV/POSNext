import { beforeEach, describe, expect, it, vi } from "vitest";

const callMock = vi.fn();
vi.mock("frappe-ui", () => ({ call: (...a) => callMock(...a) }));

import { applyVerificationPatch, fetchVerificationStatus, STATUS_URL } from "../customerVerification";

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
