import { describe, expect, it, vi } from "vitest";
import { isDeadlockError, retryOnDeadlock } from "../retryOnDeadlock";

const deadlock = () =>
	Object.assign(new Error("Internal Server Error"), { exc_type: "QueryDeadlockError" });
const noSleep = vi.fn(() => Promise.resolve());

describe("isDeadlockError", () => {
	it("recognises the error however it is reported", () => {
		expect(isDeadlockError(deadlock())).toBe(true);
		expect(
			isDeadlockError(new Error("(1213, 'Deadlock found when trying to get lock')"))
		).toBe(true);
		expect(isDeadlockError({ resourceError: { exc_type: "QueryDeadlockError" } })).toBe(true);
	});

	it("does not match real answers or empty input", () => {
		expect(
			isDeadlockError(Object.assign(new Error("x"), { exc_type: "NegativeStockError" }))
		).toBe(false);
		expect(
			isDeadlockError(
				Object.assign(new Error("Insufficient stock"), { exc_type: "ValidationError" })
			)
		).toBe(false);
		expect(isDeadlockError(null)).toBe(false);
	});
});

describe("retryOnDeadlock", () => {
	it("returns the result without retrying when the first call works", async () => {
		const fn = vi.fn().mockResolvedValue("ok");
		expect(await retryOnDeadlock(fn, { sleep: noSleep })).toBe("ok");
		expect(fn).toHaveBeenCalledTimes(1);
	});

	it("retries after a deadlock and returns the later success", async () => {
		const fn = vi.fn().mockRejectedValueOnce(deadlock()).mockResolvedValue("ok");
		const onRetry = vi.fn();
		expect(await retryOnDeadlock(fn, { sleep: noSleep, onRetry })).toBe("ok");
		expect(fn).toHaveBeenCalledTimes(2);
		expect(onRetry).toHaveBeenCalledWith(1, expect.any(Error));
	});

	it("gives up after the configured attempts and throws the deadlock", async () => {
		const fn = vi.fn().mockRejectedValue(deadlock());
		await expect(retryOnDeadlock(fn, { attempts: 3, sleep: noSleep })).rejects.toMatchObject({
			exc_type: "QueryDeadlockError",
		});
		expect(fn).toHaveBeenCalledTimes(3);
	});

	it("never retries other errors", async () => {
		const stock = Object.assign(new Error("needed in"), { exc_type: "NegativeStockError" });
		const fn = vi.fn().mockRejectedValue(stock);
		await expect(retryOnDeadlock(fn, { sleep: noSleep })).rejects.toBe(stock);
		expect(fn).toHaveBeenCalledTimes(1);
	});

	it("waits longer each time and adds jitter so collided requests do not retry in lockstep", async () => {
		const sleep = vi.fn(() => Promise.resolve());
		const fn = vi
			.fn()
			.mockRejectedValueOnce(deadlock())
			.mockRejectedValueOnce(deadlock())
			.mockResolvedValue("ok");
		await retryOnDeadlock(fn, { baseDelayMs: 100, random: () => 0.5, sleep });
		expect(sleep.mock.calls.map(([ms]) => ms)).toEqual([150, 250]);
	});
});
