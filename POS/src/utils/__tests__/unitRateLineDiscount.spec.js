import { describe, expect, it } from "vitest";
import { unitRateLineDiscount } from "../currency";

// Server figures: posnext_promotions _apply_discount (pos_next/test_minmax_unit_rate.py).
describe("unitRateLineDiscount (G6)", () => {
	it.each([
		// price, qty, blended %, line discount (base − unit rate × qty)
		[50, 2, 50, 50],
		[50, 3, 100 / 3, 50.01], // 33.33 a unit: 99.99
		[50, 4, 25, 50],
		[50, 6, 100 / 6, 49.98], // 41.67 a unit: 250.02
		[50, 7, 100 / 7, 49.98], // 42.86 a unit: 300.02
		[80, 6, 100 / 6, 79.98], // 66.67 a unit (from the unrounded %; 16.67% would give 66.66)
		[80, 7, 100 / 7, 80.01], // 68.57 a unit: 479.99
	])("%s × %s at %s percent is %s off", (price, qty, pct, discount) => {
		expect(unitRateLineDiscount(price, qty, pct)).toBe(discount);
	});

	it("100% or more frees the whole line", () => {
		expect(unitRateLineDiscount(50, 3, 100)).toBe(150);
		expect(unitRateLineDiscount(50, 3, 120)).toBe(150);
	});
});
