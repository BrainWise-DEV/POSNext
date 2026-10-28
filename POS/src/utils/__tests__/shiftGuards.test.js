/**
 * Shift close guards — pending offline expenses must not strand after close.
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";
import { canCloseShiftWithPendingExpenses } from "@/utils/shiftGuards";

describe("canCloseShiftWithPendingExpenses", () => {
	it("allows close when there are no pending expenses", () => {
		expect(canCloseShiftWithPendingExpenses(0)).toBe(true);
		expect(canCloseShiftWithPendingExpenses(null)).toBe(true);
		expect(canCloseShiftWithPendingExpenses(undefined)).toBe(true);
	});

	it("refuses close when pending expenses exist", () => {
		expect(canCloseShiftWithPendingExpenses(1)).toBe(false);
		expect(canCloseShiftWithPendingExpenses(3)).toBe(false);
	});
});
