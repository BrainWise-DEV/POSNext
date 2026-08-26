/**
 * Registry for offer discount strategies contributed by optional apps.
 *
 * `pos_next` owns the plain price-discount paths (percentage / amount / rate).
 * Modes that need cart-wide reasoning — today only `Accumulative`, owned by
 * posnext_promotions — are registered here at runtime instead of being coded
 * into posCart.js. The cart asks the registry by `offer.apply_discount_on_price`
 * and falls through to its built-in path when nothing is registered, so
 * `pos_next` never imports the satellite and stays buildable without it.
 *
 * Only the OFFLINE cart consults these. Online, the server's apply_offers is the
 * single source of truth and its result is stamped verbatim; a strategy is the
 * offline mirror of a server-side pass and must produce the same numbers.
 *
 * A strategy is a plain object:
 *
 *   {
 *     order?: number,                        // higher runs first (default 0)
 *     apply(offer, eligibleItems, ctx),      // -> boolean, true if a line changed
 *     claimsLine?(item),                     // -> boolean, this strategy owns the line
 *     allowsAutoDiscountStacking?(item),     // -> boolean, Auto Discount may stack on it
 *   }
 *
 * `ctx` carries host callbacks the strategy is not allowed to import:
 *   { recalculateItem }
 */

const strategies = new Map();

/** Register (or replace) the strategy handling one `apply_discount_on_price` mode. */
export function registerOfferStrategy(mode, strategy) {
	if (!mode || !strategy || typeof strategy.apply !== "function") {
		console.warn("[posCart] ignoring invalid offer strategy for mode:", mode);
		return;
	}
	strategies.set(mode, strategy);
}

/** The strategy for a mode, or undefined when the host should handle it itself. */
export function getOfferStrategy(mode) {
	if (!mode) return undefined;
	return strategies.get(mode);
}

/** The strategy for an offer, resolved from its cross-cart mode. */
export function getStrategyForOffer(offer) {
	return getOfferStrategy(offer?.apply_discount_on_price);
}

/**
 * Ordering weight for an offer. Strategies that claim lines exclusively must run
 * before the plain paths, or a first-come rule takes the line they needed.
 */
export function offerStrategyOrder(offer) {
	return Number(getStrategyForOffer(offer)?.order) || 0;
}

/** Whether any registered strategy allows an Auto Discount to stack on this line. */
export function allowsAutoDiscountStacking(item) {
	for (const strategy of strategies.values()) {
		if (strategy.allowsAutoDiscountStacking?.(item)) return true;
	}
	return false;
}

/** Test seam — drops every registration. */
export function clearOfferStrategies() {
	strategies.clear();
}

let loaded = null;

/**
 * Load strategy plugins shipped by installed optional apps.
 *
 * Resolved at runtime from `/assets/<app>/...`, which Frappe serves from each
 * app's `public/` directory. The URL is built at call time and marked
 * `@vite-ignore` so the bundler leaves it alone — `pos_next` must build with no
 * knowledge of the satellite. Idempotent, and a failure is non-fatal: the cart
 * keeps working with its built-in paths.
 */
export async function loadOfferStrategyPlugins() {
	if (loaded) return loaded;

	loaded = (async () => {
		const { isPromotionsAppInstalled } = await import("@/utils/promoApi");
		if (!isPromotionsAppInstalled()) return;

		const url = "/assets/posnext_promotions/pos/offer-strategies.js";
		try {
			const plugin = await import(/* @vite-ignore */ url);
			await plugin.register?.({ registerOfferStrategy });
		} catch (error) {
			console.error("[posCart] failed to load promotions offer strategies:", error);
		}
	})();

	return loaded;
}
