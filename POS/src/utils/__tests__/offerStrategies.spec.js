import { beforeEach, describe, expect, it, vi } from "vitest";
import {
	allowsAutoDiscountStacking,
	clearOfferStrategies,
	getOfferStrategy,
	getStrategyForOffer,
	offerStrategyOrder,
	registerOfferStrategy,
} from "@/utils/offerStrategies";

/**
 * The registry is pos_next's half of the offer-strategy seam. It must stay
 * usable with nothing registered — that is the shape a site without
 * posnext_promotions runs in — and must never need to know a mode's name.
 */
describe("offer strategy registry", () => {
	beforeEach(() => clearOfferStrategies());

	it("resolves nothing when no app has registered", () => {
		expect(getOfferStrategy("Accumulative")).toBeUndefined();
		expect(getStrategyForOffer({ apply_discount_on_price: "Accumulative" })).toBeUndefined();
		expect(offerStrategyOrder({ apply_discount_on_price: "Accumulative" })).toBe(0);
		expect(allowsAutoDiscountStacking({ is_accumulative_discount: 1 })).toBe(false);
	});

	it("resolves a registered strategy by the offer's cross-cart mode", () => {
		const strategy = { order: 100, apply: () => true };
		registerOfferStrategy("Accumulative", strategy);

		expect(getStrategyForOffer({ apply_discount_on_price: "Accumulative" })).toBe(strategy);
		expect(getStrategyForOffer({ apply_discount_on_price: "Min" })).toBeUndefined();
		expect(getStrategyForOffer({})).toBeUndefined();
	});

	it("orders strategy-backed offers ahead of plain ones", () => {
		registerOfferStrategy("Accumulative", { order: 100, apply: () => true });

		const offers = [
			{ name: "plain" },
			{ name: "accum", apply_discount_on_price: "Accumulative" },
			{ name: "other", apply_discount_on_price: "Min" },
		];
		const ordered = [...offers].sort((a, b) => offerStrategyOrder(b) - offerStrategyOrder(a));

		expect(ordered[0].name).toBe("accum");
	});

	it("delegates the Auto Discount stacking decision to the strategy", () => {
		registerOfferStrategy("Accumulative", {
			apply: () => true,
			allowsAutoDiscountStacking: (item) => Boolean(item.is_accumulative_discount),
		});

		expect(allowsAutoDiscountStacking({ is_accumulative_discount: 1 })).toBe(true);
		expect(allowsAutoDiscountStacking({})).toBe(false);
	});

	it("rejects a malformed registration instead of breaking the cart", () => {
		const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

		registerOfferStrategy("Accumulative", { order: 1 }); // no apply()
		registerOfferStrategy("", { apply: () => true });

		expect(getOfferStrategy("Accumulative")).toBeUndefined();
		expect(warn).toHaveBeenCalled();
		warn.mockRestore();
	});
});
