import { describe, expect, it } from "vitest";
import { CoalescingMutex } from "../mutex";
import { createSubmitRequestTracker, isSubmitTimeoutError } from "../submitRequestId";

const counter = () => {
	let n = 0;
	return () => `id-${++n}`;
};

describe("createSubmitRequestTracker", () => {
	it("reuses the key for an identical payload (retry after a timeout)", () => {
		const t = createSubmitRequestTracker(counter());
		const payload = { items: [{ item_code: "A", qty: 1 }], customer: "C" };
		const first = t.idFor(payload);
		expect(t.idFor({ ...payload })).toBe(first);
	});

	it("rotates the key when the cart changes", () => {
		const t = createSubmitRequestTracker(counter());
		const first = t.idFor({ items: [{ item_code: "A", qty: 1 }] });
		expect(t.idFor({ items: [{ item_code: "A", qty: 2 }] })).not.toBe(first);
	});

	it("rotates the key after reset (next sale)", () => {
		const t = createSubmitRequestTracker(counter());
		const payload = { items: [] };
		const first = t.idFor(payload);
		t.reset();
		expect(t.idFor(payload)).not.toBe(first);
	});

	it("generates a unique default key", () => {
		const a = createSubmitRequestTracker().idFor({ a: 1 });
		const b = createSubmitRequestTracker().idFor({ a: 1 });
		expect(a).toMatch(/^pos_online_/);
		expect(a).not.toBe(b);
	});
});

describe("submit timeout handling", () => {
	it("recognises the mutex timeout error", async () => {
		const mutex = new CoalescingMutex({ timeout: 20, name: "InvoiceSubmit" });
		let caught;
		try {
			await mutex.withLock(() => new Promise(() => {}));
		} catch (e) {
			caught = e;
		}
		expect(isSubmitTimeoutError(caught)).toBe(true);
		expect(caught.message).toContain("InvoiceSubmit: Operation timed out after 20ms");
	});

	it("does not treat other errors as timeouts", () => {
		expect(isSubmitTimeoutError(new Error("Insufficient stock"))).toBe(false);
		expect(isSubmitTimeoutError(null)).toBe(false);
	});

	it("lets a new submit start after a timeout (lock is released)", async () => {
		const mutex = new CoalescingMutex({ timeout: 20, name: "InvoiceSubmit" });
		await expect(mutex.withLock(() => new Promise(() => {}))).rejects.toThrow(/timed out/);
		expect(mutex.isLocked).toBe(false);
		await expect(mutex.withLock(async () => "ok")).resolves.toBe("ok");
	});
});
