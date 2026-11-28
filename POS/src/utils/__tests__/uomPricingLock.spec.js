import { describe, expect, it } from "vitest";
import {
	isFreePromoRow,
	scaleRateForUomChange,
	shouldPreserveRateOnUomChange,
} from "../uomPricingLock";

describe("uomPricingLock", () => {
	it("treats free / standalone GWP rows as promo-owned", () => {
		expect(isFreePromoRow({ is_free_item: 1 })).toBe(true);
		expect(isFreePromoRow({ _isStandaloneFreeRow: true })).toBe(true);
		expect(isFreePromoRow({ is_free_item: 0 })).toBe(false);
	});

	it("preserves rate on UOM change for free, promo-sourced, and manual rates", () => {
		expect(shouldPreserveRateOnUomChange({ is_free_item: 1, rate: 0 })).toBe(true);
		expect(
			shouldPreserveRateOnUomChange({
				discount_source: "item_level_promotion",
				rate: 8,
			})
		).toBe(true);
		expect(
			shouldPreserveRateOnUomChange({
				discount_source: "accumulative_promotion",
				rate: 8,
			})
		).toBe(true);
		expect(
			shouldPreserveRateOnUomChange({
				is_rate_manually_edited: 1,
				rate: 9,
			})
		).toBe(true);
		expect(
			shouldPreserveRateOnUomChange({
				discount_source: "manual_discount",
				rate: 9,
			})
		).toBe(false);
		expect(shouldPreserveRateOnUomChange({ rate: 10 })).toBe(false);
	});

	it("scales rates by conversion factor so free stays zero", () => {
		expect(scaleRateForUomChange(0, 1, 12)).toBe(0);
		expect(scaleRateForUomChange(10, 1, 12)).toBe(120);
		expect(scaleRateForUomChange(120, 12, 1)).toBe(10);
	});
});
