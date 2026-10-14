/**
 * Cart lines discounted by a POS Coupon priced per line by posnext_promotions.
 *
 * Amount coupons and capped percentage coupons arrive as a fixed line discount.
 * recalculateItem() turns a fixed amount into a percentage, so without a cap a
 * quantity increase would grow the discount past what the coupon allows until
 * the server re-prices the cart — and offline it never does.
 *
 * A coupon can stack on a discount the line already had (a promotion, when the
 * coupon does not exclude discounted items). That discount is kept in
 * `pre_coupon_discount` so offers and coupon checks see the line without the
 * coupon, and removing the coupon gives it back.
 */

export const COUPON_DISCOUNT_SOURCE = "coupon";

const NO_DISCOUNT = Object.freeze({
	discount_percentage: 0,
	discount_amount: 0,
	discount_source: "",
	is_already_discounted: 0,
});

export function isCouponLine(item) {
	return item?.discount_source === COUPON_DISCOUNT_SOURCE && Boolean(item.coupon_code);
}

/** Discount fields of the line as if the coupon were not applied. */
export function preCouponDiscount(item) {
	if (isCouponLine(item)) return item.pre_coupon_discount || NO_DISCOUNT;
	return {
		discount_percentage: item.discount_percentage || 0,
		discount_amount: item.discount_amount || 0,
		discount_source: item.discount_source || "",
		is_already_discounted: item.is_already_discounted || 0,
	};
}

export function stashPreCouponDiscount(item) {
	item.pre_coupon_discount = { ...preCouponDiscount(item) };
}

export function restorePreCouponDiscount(item) {
	const pre = item.pre_coupon_discount || NO_DISCOUNT;
	item.discount_percentage = pre.discount_percentage || 0;
	item.discount_amount = pre.discount_amount || 0;
	item.discount_source = pre.discount_source || "";
	item.is_already_discounted = pre.is_already_discounted || 0;
	item.pre_coupon_discount = null;
}

/** Line discount the line would carry without the coupon, at its current quantity (as recalculateItem). */
export function preCouponLineDiscount(item) {
	const pre = preCouponDiscount(item);
	const unitPrice =
		item.is_rate_manually_edited === 1 ? Number(item.rate) || 0 : Number(item.price_list_rate || item.rate) || 0;
	const base = unitPrice * (Number(item.quantity) || 0);
	if (pre.discount_percentage > 0) return (base * pre.discount_percentage) / 100;
	return Math.min(Number(pre.discount_amount) || 0, base);
}

export function hasFixedCouponDiscount(item) {
	return isCouponLine(item) && item.coupon_fixed_discount != null;
}

/**
 * Largest discount a fixed coupon line may carry at its current quantity:
 * never more than the server allocated, the line itself, or the coupon's
 * percentage of the line when the coupon is a capped percentage.
 * Rounded down to a whole per-unit amount so the per-unit rate reproduces it
 * exactly and currency rounding can't push it over the limit.
 */
export function fixedCouponLineDiscount(item, precision = 2) {
	const unitPrice = Number(item.price_list_rate || item.rate) || 0;
	const qty = Number(item.quantity) || 0;
	if (qty <= 0) return 0;
	const base = unitPrice * qty;
	let allowed = Math.min(Number(item.coupon_fixed_discount) || 0, base);
	const percentage = Number(item.coupon_percentage_cap) || 0;
	if (percentage > 0) {
		allowed = Math.min(allowed, (base * percentage) / 100);
	}
	const factor = 10 ** precision;
	const perUnit = Math.max(Math.floor((allowed / qty) * factor + 1e-6), 0);
	return Math.round(perUnit * qty) / factor;
}
