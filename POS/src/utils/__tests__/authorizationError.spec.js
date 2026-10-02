import { describe, expect, it } from "vitest";
import { isAuthorizationError, isRateLimitError } from "@/utils/authorizationError";


describe("isAuthorizationError", () => {
	it("matches the real _server_messages payload the gate produces", () => {
		const error = {
			_server_messages: JSON.stringify([
				JSON.stringify({
					message: "Sales Invoice Return requires authorization by: Nexus POS Manager",
					title: "Authorization Required",
					indicator: "red",
					raise_exception: 1,
				}),
			]),
		};

		expect(isAuthorizationError(error)).toBe(true);
	});

	it("matches when the title arrives on other error shapes", () => {
		expect(isAuthorizationError({ messages: ["Authorization Required"] })).toBe(true);
		expect(isAuthorizationError({ message: "Authorization Required" })).toBe(true);
		expect(isAuthorizationError({ exc: "...\nTitle: Authorization Required\n" })).toBe(true);
	});

	it("does not match unrelated failures", () => {
		expect(isAuthorizationError(null)).toBe(false);
		expect(isAuthorizationError({})).toBe(false);
		expect(isAuthorizationError({ message: "Insufficient stock for SKU001" })).toBe(false);
		expect(
			isAuthorizationError({
				_server_messages: JSON.stringify([
					JSON.stringify({ message: "Negative stock", title: "Validation Error" }),
				]),
			})
		).toBe(false);
	});

	it("survives malformed _server_messages instead of throwing", () => {
		expect(isAuthorizationError({ _server_messages: "not json" })).toBe(false);
		expect(isAuthorizationError({ _server_messages: "Authorization Required" })).toBe(true);
	});
});

describe("isRateLimitError", () => {
	it("matches Frappe's 429 exception type", () => {
		expect(isRateLimitError({ exc_type: "RateLimitExceededError" })).toBe(true);
	});

	it("matches an explicit 429 status", () => {
		expect(isRateLimitError({ httpStatus: 429 })).toBe(true);
		expect(isRateLimitError({ status: 429 })).toBe(true);
	});

	it("matches Frappe's stock rate-limit wording in _server_messages", () => {
		const error = {
			_server_messages: JSON.stringify([
				JSON.stringify({
					message:
						"You hit the rate limit because of too many requests. Please try after sometime.",
					indicator: "red",
				}),
			]),
		};
		expect(isRateLimitError(error)).toBe(true);
	});

	it("does not confuse a gate refusal with a rate limit", () => {
		const gateRefusal = {
			_server_messages: JSON.stringify([
				JSON.stringify({
					message: "Sales Invoice Return requires authorization by: Nexus POS Manager",
					title: "Authorization Required",
				}),
			]),
		};
		expect(isRateLimitError(gateRefusal)).toBe(false);
		expect(isAuthorizationError(gateRefusal)).toBe(true);
	});

	it("does not match unrelated failures", () => {
		expect(isRateLimitError(null)).toBe(false);
		expect(isRateLimitError({})).toBe(false);
		expect(isRateLimitError({ message: "Incorrect PIN" })).toBe(false);
		expect(isRateLimitError({ httpStatus: 417 })).toBe(false);
	});
});
