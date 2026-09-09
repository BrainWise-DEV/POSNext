import { describe, expect, it } from "vitest";
import { buildAuthorizationSummary } from "@/utils/authorizationSummary";

const formatAmount = (value) => `EGP ${value.toFixed(2)}`;
const build = (state) => buildAuthorizationSummary(state, { formatAmount });
const byKey = (rows) => Object.fromEntries(rows.map((r) => [r.key, r.value]));


describe("buildAuthorizationSummary", () => {
	it("shows action, refund amount and source invoice for a return", () => {
		const rows = build({
			action: "Sales Invoice Return",
			actionLabel: "",
			context: {
				pos_profile: "Cairo Branch",
				return_against: "ACC-SINV-2026-00212",
				customer: "Walk In",
				amount: 237.5,
			},
		});

		expect(rows.map((r) => r.key)).toEqual(["action", "amount", "return_against"]);
		expect(byKey(rows)).toEqual({
			action: "Sales Invoice Return",
			amount: "EGP 237.50",
			return_against: "ACC-SINV-2026-00212",
		});
	});

	it("prefers an explicit actionLabel over the registry action name", () => {
		const rows = build({
			action: "Sales Invoice Return",
			actionLabel: "Refund to card",
			context: { amount: 10 },
		});

		expect(byKey(rows).action).toBe("Refund to card");
	});

	it("omits the invoice row for a return with no original invoice", () => {
		const rows = build({
			action: "Sales Return Without Invoice",
			context: { pos_profile: "Cairo Branch", amount: 50 },
		});

		expect(rows.map((r) => r.key)).toEqual(["action", "amount"]);
		expect(byKey(rows).action).toBe("Sales Return Without Invoice");
	});

	it("omits the amount row when the action carries no amount", () => {
		const rows = build({ action: "Discount Override", context: { pos_profile: "Cairo Branch" } });

		expect(rows.map((r) => r.key)).toEqual(["action"]);
	});

	it("treats a zero or unparseable amount as nothing to show", () => {
		expect(build({ action: "X", context: { amount: 0 } }).map((r) => r.key)).toEqual(["action"]);
		expect(build({ action: "X", context: { amount: null } }).map((r) => r.key)).toEqual(["action"]);
		expect(build({ action: "X", context: { amount: "abc" } }).map((r) => r.key)).toEqual(["action"]);
	});

	it("accepts a numeric string amount, as JSON round-trips can produce", () => {
		expect(byKey(build({ action: "X", context: { amount: "237.5" } })).amount).toBe("EGP 237.50");
	});

	it("renders nothing rather than throwing when state is empty", () => {
		expect(build({})).toEqual([]);
		expect(buildAuthorizationSummary(undefined, { formatAmount })).toEqual([]);
		expect(build({ action: "X" }).map((r) => r.key)).toEqual(["action"]);
	});

	it("labels every row it returns", () => {
		const rows = build({
			action: "Sales Invoice Return",
			context: { return_against: "ACC-SINV-1", amount: 1 },
		});

		for (const row of rows) {
			expect(row.label).toBeTruthy();
			expect(row.value).toBeTruthy();
		}
	});
});
