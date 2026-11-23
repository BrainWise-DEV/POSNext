/**
 * Sales Orders carry no Friends & Family discount (Phase 2 Task 8f).
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";
import { stripFnfKeys, stripFriendsAndFamilyForOrder } from "@/utils/friendsAndFamily";

const ffLine = {
	item_code: "A",
	qty: 2,
	price_list_rate: 100,
	rate: 70,
	amount: 140,
	discount_percentage: 30,
	discount_amount: 60,
	posnext_discount_source: "friends_and_family",
	posnext_fnf_percentage: 30,
	posnext_fnf_amount: 60,
};
const manualLine = {
	item_code: "B",
	qty: 1,
	price_list_rate: 100,
	rate: 90,
	discount_percentage: 10,
	discount_amount: 10,
	posnext_discount_source: "manual",
};

describe("stripFriendsAndFamilyForOrder", () => {
	it("strips ff lines for sales order", () => {
		const { items, stripped } = stripFriendsAndFamilyForOrder([ffLine]);
		expect(stripped).toBe(1);
		expect(items[0].discount_percentage).toBe(0);
		expect(items[0].discount_amount).toBe(0);
		expect(items[0].rate).toBe(100);
		expect(items[0].amount).toBe(200);
		expect(Object.keys(items[0]).some((k) => k.startsWith("posnext_fnf_"))).toBe(false);
		expect(ffLine.discount_percentage).toBe(30); // input untouched
	});

	it("strips cart lines marked by discount_source", () => {
		const cartLine = { quantity: 1, price_list_rate: 50, rate: 40, amount: 40, discount_amount: 10, discount_source: "friends_and_family", fnf_reason: "applied" };
		const { items, stripped } = stripFriendsAndFamilyForOrder([cartLine]);
		expect(stripped).toBe(1);
		expect(items[0]).toMatchObject({ rate: 50, amount: 50, discount_amount: 0, discount_source: "" });
		expect(items[0].fnf_reason).toBeUndefined();
	});

	it("keeps non-ff discounts", () => {
		const { items, stripped } = stripFriendsAndFamilyForOrder([manualLine]);
		expect(stripped).toBe(0);
		expect(items[0]).toEqual(manualLine);
	});

	it("strips header keys", () => {
		expect(stripFnfKeys({ a: 1, posnext_fnf_total: 5 })).toEqual({ a: 1 });
	});
});
