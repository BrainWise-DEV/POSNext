import { describe, expect, it } from "vitest";
import { buildCouponItemsSnapshot, unwrapCouponValidation } from "../invoice";

describe("unwrapCouponValidation", () => {
	it("returns the payload whether or not frappe wrapped it in message", () => {
		const payload = {
			valid: true,
			message: "Coupon applied successfully",
			line_updates: [],
		};
		expect(unwrapCouponValidation(payload)).toBe(payload);
		expect(unwrapCouponValidation({ message: payload })).toBe(payload);
		expect(unwrapCouponValidation({ message: "Invalid coupon code" })).toEqual({
			valid: false,
			message: "Invalid coupon code",
		});
		expect(unwrapCouponValidation(null)).toBeNull();
	});
});

describe("buildCouponItemsSnapshot", () => {
	it("sends the pre-coupon discount for lines that already carry the coupon", () => {
		const [plain, couponed, couponedNoOffer] = buildCouponItemsSnapshot([
			{
				item_code: "A",
				quantity: 2,
				rate: 50,
				price_list_rate: 50,
				discount_percentage: 10,
			},
			{
				item_code: "B",
				quantity: 1,
				rate: 100,
				price_list_rate: 100,
				discount_percentage: 30,
				coupon_code: "SAVE20",
				pre_coupon_discount_percentage: 10,
			},
			{
				item_code: "C",
				quantity: 1,
				rate: 80,
				discount_amount: 16,
				coupon_code: "SAVE20",
				discount_source: "manual_discount",
				is_already_discounted: 1,
			},
		]);

		expect(plain).toMatchObject({
			item_code: "A",
			qty: 2,
			discount_percentage: 10,
			idx: 1,
		});
		expect(couponed).toMatchObject({
			discount_percentage: 10,
			discount_amount: 0,
			idx: 2,
		});
		expect(couponedNoOffer).toMatchObject({
			discount_percentage: 0,
			discount_amount: 0,
			price_list_rate: 80,
			discount_source: "",
			is_already_discounted: 0,
		});
	});
});
