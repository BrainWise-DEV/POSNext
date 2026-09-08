/**
 * Registry for offer discount strategies contributed by optional apps.
 *
 * `pos_next` owns the plain price-discount paths (percentage / amount / rate)
 * and the plain free-item path (same_item / free_item). Modes and promotion
 * types that need cart-wide reasoning — Accumulative, Gift Pool, GWP — are
 * owned by posnext_promotions and registered here at runtime instead of being
 * coded into posCart.js. The cart asks the registry and falls through to its
 * built-in path when nothing is registered, so `pos_next` never imports the
 * satellite and stays buildable without it.
 *
 * Only the OFFLINE cart consults these. Online, the server's apply_offers is the
 * single source of truth and its result is stamped verbatim; a strategy is the
 * offline mirror of a server-side pass and must produce the same numbers.
 *
 * Price strategies key on `offer.apply_discount_on_price` (e.g. Accumulative).
 * Product strategies key on `offer.promotion_type` (e.g. Gift Pool, GWP).
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
 *   { recalculateItem, invoiceItems }
 */

const priceStrategies = new Map();
const productStrategies = new Map();

/** Register (or replace) the strategy handling one `apply_discount_on_price` mode. */
export function registerOfferStrategy(mode, strategy) {
	if (!mode || !strategy || typeof strategy.apply !== "function") {
		console.warn("[posCart] ignoring invalid offer strategy for mode:", mode);
		return;
	}
	priceStrategies.set(mode, strategy);
}

/**
 * Register (or replace) the strategy handling one product `promotion_type`
 * (Give Product offline path).
 */
export function registerProductOfferStrategy(promotionType, strategy) {
	if (!promotionType || !strategy || typeof strategy.apply !== "function") {
		console.warn(
			"[posCart] ignoring invalid product offer strategy for type:",
			promotionType
		);
		return;
	}
	productStrategies.set(promotionType, strategy);
}

/** The price strategy for a mode, or undefined when the host should handle it itself. */
export function getOfferStrategy(mode) {
	if (!mode) return undefined;
	return priceStrategies.get(mode);
}

/** The strategy for an offer, resolved from its cross-cart price mode. */
export function getStrategyForOffer(offer) {
	return getOfferStrategy(offer?.apply_discount_on_price);
}

/** The product strategy for a promotion_type, or undefined. */
export function getProductOfferStrategy(promotionType) {
	if (!promotionType) return undefined;
	return productStrategies.get(promotionType);
}

/** The product strategy for an offer, resolved from its promotion_type. */
export function getProductStrategyForOffer(offer) {
	return getProductOfferStrategy(offer?.promotion_type);
}

/**
 * Ordering weight for an offer. Strategies that claim lines exclusively must run
 * before the plain paths, or a first-come rule takes the line they needed.
 */
export function offerStrategyOrder(offer) {
	const priceOrder = Number(getStrategyForOffer(offer)?.order) || 0;
	const productOrder = Number(getProductStrategyForOffer(offer)?.order) || 0;
	return Math.max(priceOrder, productOrder);
}

/** Whether any registered strategy allows an Auto Discount to stack on this line. */
export function allowsAutoDiscountStacking(item) {
	for (const strategy of priceStrategies.values()) {
		if (strategy.allowsAutoDiscountStacking?.(item)) return true;
	}
	for (const strategy of productStrategies.values()) {
		if (strategy.allowsAutoDiscountStacking?.(item)) return true;
	}
	return false;
}

/** Test seam — drops every registration. */
export function clearOfferStrategies() {
	priceStrategies.clear();
	productStrategies.clear();
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
			await plugin.register?.({
				registerOfferStrategy,
				registerProductOfferStrategy,
			});
		} catch (error) {
			console.error("[posCart] failed to load promotions offer strategies:", error);
		}
	})();

	return loaded;
}
