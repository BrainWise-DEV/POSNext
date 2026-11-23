/**
 * D-R4-09 (c): when a submit's answer is lost (the request may have reached the
 * server), the cashier is not told "Unable to connect … check your internet": the sale
 * may be saved, and Try Again checks it without making a second one.
 */
import { describe, expect, it, vi } from "vitest"

vi.hoisted(() => {
	globalThis.__ = (s) => s
})

const { submitErrorContext } = await import("../errorHandler")

const lost = new TypeError("Failed to fetch")

describe("a submit with no answer (D-R4-09 c)", () => {
	it("says the sale may be saved, and that Try Again makes no second sale", () => {
		const context = submitErrorContext(lost, { outcomeUnknown: true })
		expect(context.message).not.toContain("Unable to connect")
		expect(context.message).toContain("may already be saved")
		expect(context.message).toContain("never makes a second sale")
		expect(context.retryable).toBe(true)
	})

	it("a request that never left keeps the connection message", () => {
		expect(submitErrorContext(lost, { outcomeUnknown: false }).message).toContain("Unable to connect")
	})

	it("a server refusal is unchanged", () => {
		const refused = { exc_type: "ValidationError", httpStatus: 417, messages: ["Row 1: over the limit"] }
		expect(submitErrorContext(refused, { outcomeUnknown: true }).message).toBe("Row 1: over the limit")
	})
})
