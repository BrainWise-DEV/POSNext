import { describe, expect, it, vi } from "vitest";
import { SKIPPED, SkipIfBusyMutex } from "../mutex";
import { createSubmitRequestTracker, isSubmitTimeoutError } from "../submitRequestId";
import { recoverTimedOutSubmit } from "../submitTimeoutRecovery";

const deferred = () => {
	let resolve;
	const promise = new Promise((r) => {
		resolve = r;
	});
	return { promise, resolve };
};

describe("SkipIfBusyMutex", () => {
	it("runs the first caller and drops a double-click without re-running it", async () => {
		const gate = new SkipIfBusyMutex({ timeout: 1000, name: "InvoiceSubmit" });
		const first = deferred();
		const submit = vi.fn(() => first.promise);

		const a = gate.run(submit);
		const b = gate.run(submit); // double-click while the first is in flight
		expect(await b).toBe(SKIPPED);

		first.resolve("INV-1");
		expect(await a).toBe("INV-1");

		// The dropped call must not run later against an already cleared cart.
		await Promise.resolve();
		expect(submit).toHaveBeenCalledTimes(1);
		expect(gate.isLocked).toBe(false);
	});

	it("accepts a new submit after the previous one finished or failed", async () => {
		const gate = new SkipIfBusyMutex({ timeout: 1000 });
		await expect(gate.run(async () => 1)).resolves.toBe(1);
		await expect(gate.run(async () => Promise.reject(new Error("boom")))).rejects.toThrow(
			"boom"
		);
		await expect(gate.run(async () => 2)).resolves.toBe(2);
	});

	it("releases the gate on timeout with the recognisable error, without cancelling the work", async () => {
		const gate = new SkipIfBusyMutex({ timeout: 20, name: "InvoiceSubmit" });
		const never = deferred();
		const started = vi.fn(() => never.promise);

		let error;
		try {
			await gate.run(started);
		} catch (e) {
			error = e;
		}
		expect(isSubmitTimeoutError(error)).toBe(true);
		expect(error.message).toBe("InvoiceSubmit: Operation timed out after 20ms");
		expect(gate.isLocked).toBe(false);
		await expect(gate.run(async () => "retry")).resolves.toBe("retry");
	});
});

describe("recoverTimedOutSubmit", () => {
	const noSleep = () => Promise.resolve();

	it("returns the invoice summary as soon as the server reports the sale", async () => {
		const invoice = { name: "ACC-SINV-1", grand_total: 120, status: 1 };
		const check = vi
			.fn()
			.mockResolvedValueOnce({ synced: false })
			.mockResolvedValueOnce({ synced: true, sales_invoice: "ACC-SINV-1", invoice });
		const result = await recoverTimedOutSubmit("req-1", { check, sleep: noSleep });
		expect(result).toEqual(invoice);
		expect(check).toHaveBeenCalledTimes(2);
		expect(check).toHaveBeenCalledWith("req-1");
	});

	it("falls back to the invoice name when no totals are returned", async () => {
		const check = vi.fn().mockResolvedValue({ synced: true, sales_invoice: "ACC-SINV-2" });
		const result = await recoverTimedOutSubmit("req-2", { check, sleep: noSleep });
		expect(result).toMatchObject({ name: "ACC-SINV-2", status: 1 });
	});

	it("gives up after the configured attempts and returns null", async () => {
		const check = vi.fn().mockResolvedValue({ synced: false });
		const result = await recoverTimedOutSubmit("req-3", {
			check,
			attempts: 3,
			sleep: noSleep,
		});
		expect(result).toBeNull();
		expect(check).toHaveBeenCalledTimes(3);
	});

	it("keeps trying when a status check itself fails", async () => {
		const invoice = { name: "ACC-SINV-3" };
		const check = vi
			.fn()
			.mockRejectedValueOnce(new Error("network"))
			.mockResolvedValueOnce({ synced: true, invoice });
		expect(await recoverTimedOutSubmit("req-4", { check, sleep: noSleep })).toEqual(invoice);
	});

	it("does nothing without a request id", async () => {
		const check = vi.fn();
		expect(await recoverTimedOutSubmit(null, { check, sleep: noSleep })).toBeNull();
		expect(check).not.toHaveBeenCalled();
	});
});

describe("submit request tracker", () => {
	it("exposes the key of the checkout in progress", () => {
		const tracker = createSubmitRequestTracker(() => "key-1");
		expect(tracker.current()).toBeNull();
		tracker.idFor({ a: 1 });
		expect(tracker.current()).toBe("key-1");
		tracker.reset();
		expect(tracker.current()).toBeNull();
	});
});
