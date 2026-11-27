import { describe, expect, it } from "vitest";
import { classifyCheckoutError } from "../checkoutErrors";
import { isDeadlockError } from "../retryOnDeadlock";

const err = (message, extra = {}) => Object.assign(new Error(message), extra);

describe("classifyCheckoutError", () => {
	it("1213 is a deadlock and may be retried automatically", () => {
		const e = err(
			"(1213, 'Deadlock found when trying to get lock; try restarting transaction')",
			{
				exc_type: "QueryDeadlockError",
			}
		);
		expect(classifyCheckoutError(e)).toEqual({ kind: "deadlock", autoRetry: true });
	});

	it("1020 (snapshot conflict) reaches the screen as QueryDeadlockError and is retried too", () => {
		const e = err("(1020, 'Record has changed since last read in table')", {
			exc_type: "QueryDeadlockError",
		});
		expect(classifyCheckoutError(e)).toEqual({ kind: "snapshot_conflict", autoRetry: true });
	});

	it("1205 is a lock wait timeout and is NEVER retried automatically", () => {
		const e = err("(1205, 'Lock wait timeout exceeded; try restarting transaction')", {
			exc_type: "QueryTimeoutError",
		});
		expect(classifyCheckoutError(e)).toEqual({ kind: "lock_wait_timeout", autoRetry: false });
		expect(isDeadlockError(e)).toBe(false);
	});

	it("the exception type alone is enough when the number is missing", () => {
		expect(
			classifyCheckoutError(err("Internal Server Error", { exc_type: "QueryTimeoutError" }))
				.kind
		).toBe("lock_wait_timeout");
		expect(
			classifyCheckoutError(err("Internal Server Error", { exc_type: "QueryDeadlockError" }))
				.kind
		).toBe("deadlock");
	});

	it("the screen's own 60 s limit and network failures are separate kinds, never auto-retried", () => {
		const timeout = err("InvoiceSubmit: Operation timed out after 60000ms");
		expect(classifyCheckoutError(timeout)).toEqual({
			kind: "frontend_timeout",
			autoRetry: false,
		});
		for (const e of [
			err("Failed to fetch"),
			err("x", { httpStatus: 504 }),
			err("x", { httpStatus: 0 }),
		]) {
			expect(classifyCheckoutError(e)).toEqual({ kind: "network", autoRetry: false });
		}
	});

	it("real answers (stock, validation) are 'other' and never retried", () => {
		const e = err("1 units needed in", { exc_type: "NegativeStockError" });
		expect(classifyCheckoutError(e)).toEqual({ kind: "other", autoRetry: false });
		expect(classifyCheckoutError(null).kind).toBe("other");
	});
});
