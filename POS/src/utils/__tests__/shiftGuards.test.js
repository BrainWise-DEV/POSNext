/**
 * Shift close guards — pending offline expenses must not strand after close.
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";
import { canCloseShiftWithPendingExpenses, closingShiftPayload, openDraftsNotice } from "@/utils/shiftGuards";

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

describe("D-R2-18: open drafts on the shift", () => {
	const drafts = [
		{ name: "ACC-SINV-1", customer_name: "A", grand_total: 50 },
		{ name: "ACC-SINV-2", customer_name: "B", grand_total: 70 },
	];

	it("lists them and says they are deleted at close when the profile deletes drafts", () => {
		const notice = openDraftsNotice({ open_drafts: drafts, open_drafts_deleted_on_close: true });
		expect(notice.drafts.map((d) => d.name)).toEqual(["ACC-SINV-1", "ACC-SINV-2"]);
		expect(notice.title).toBe("2 draft invoice(s) are still open on this shift");
		expect(notice.detail).toContain("deleted when you close the shift");
	});

	it("says they stay open otherwise", () => {
		const notice = openDraftsNotice({ open_drafts: drafts.slice(0, 1), open_drafts_deleted_on_close: false });
		expect(notice.detail).toContain("stay open after you close the shift");
	});

	it("no drafts → no notice", () => {
		expect(openDraftsNotice({ open_drafts: [] })).toBeNull();
		expect(openDraftsNotice({})).toBeNull();
		expect(openDraftsNotice(null)).toBeNull();
	});

	it("the closing shift sent to the server leaves the display-only drafts out", () => {
		const payload = closingShiftPayload({ name: "X", open_drafts: drafts, open_drafts_deleted_on_close: true, grand_total: 1 });
		expect(payload).toEqual({ name: "X", grand_total: 1 });
	});
});
