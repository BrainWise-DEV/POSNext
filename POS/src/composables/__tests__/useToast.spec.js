/** Toasts show one at a time and the latest wins. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.hoisted(() => {
	globalThis.__ = (s) => s;
});

const { useToast } = await import("../useToast");

describe("useToast", () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => {
		useToast().clearAllToasts();
		vi.useRealTimers();
	});

	it("replaces the visible toast instead of queueing", () => {
		const toast = useToast();
		toast.showSuccess("first");
		toast.showInfo("second");
		expect(toast.toastNotification.value).toMatchObject({ message: "second", type: "info" });
		expect(toast.toastQueue.value).toHaveLength(0);
		vi.advanceTimersByTime(10000);
		expect(toast.showToast.value).toBe(false);
	});

	it("keeps the latest toast for its full duration", () => {
		const toast = useToast();
		toast.showSuccess("first");
		vi.advanceTimersByTime(3000);
		toast.showError("second");
		vi.advanceTimersByTime(3000);
		expect(toast.showToast.value).toBe(true);
		expect(toast.toastNotification.value.message).toBe("second");
	});

	it("titles warnings as a notice, not a validation error", () => {
		const toast = useToast();
		toast.showWarning("Offer removed");
		expect(toast.toastNotification.value.title).toBe("Warning");
	});
});
