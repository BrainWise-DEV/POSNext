/**
 * Cart lines discounted by a scoped POS Coupon (Item Code / Item Group / Brand).
 *
 * Amount coupons and capped percentage coupons arrive as a fixed line discount.
 * recalculateItem() turns a fixed amount into a percentage, so without a cap a
 * quantity increase would grow the discount past what the coupon allows until
 * the server re-prices the cart — and offline it never does.
 */

export const COUPON_DISCOUNT_SOURCE = "coupon";

export function isCouponLine(item) {
	return item?.discount_source === COUPON_DISCOUNT_SOURCE && Boolean(item.coupon_code);
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
