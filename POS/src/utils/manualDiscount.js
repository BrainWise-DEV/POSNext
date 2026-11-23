/**
 * Manual line discount limits (Edit Item dialog), as the server enforces them:
 * a cashier's discount stays below 100% of the line (a gift is an offer, never a
 * manual 100%), and Max Discount Percentage Allowed caps the whole reduction
 * from list price (rate edit plus discount). 0 = no limit.
 */

import { roundCurrency, unitRoundedAmountDiscount } from "@/utils/currency";

/**
 * The fixed discount the cashier asked for on a line. The line holds it as whole cents
 * a unit (G8), so while `discount_amount` is still the cart's own rounding of the
 * request, the request is what counts: a qty change splits it again. Anything that
 * writes the amount (the cashier, the server, a coupon) clears `_unit_discount_amount`
 * or writes another figure, and its figure becomes the request.
 */
export function requestedDiscountAmount(item) {
	const amount = Number(item?.discount_amount) || 0;
	const requested = Number(item?._requested_discount_amount) || 0;
	const ownRounding = item?._unit_discount_amount != null && amount === item._unit_discount_amount;
	return requested > 0 && ownRounding ? requested : amount;
}

/**
 * What a fixed amount becomes on the line when it does not split into whole cents a
 * unit (10 off 3 units is 9.99, 3.33 a unit), or null when it is applied as typed.
 * @returns {{applied: number, perUnit: number}|null}
 */
export function appliedAmountHint({ amount, qty, subtotal }) {
	const asked = roundCurrency(Number(amount) || 0);
	const units = Number(qty) || 0;
	if (asked <= 0 || units <= 0) return null;
	const applied = unitRoundedAmountDiscount(asked, units, subtotal);
	if (Math.abs(applied - Math.min(asked, Number(subtotal) || 0)) < 1e-9) return null;
	return { applied, perUnit: roundCurrency(applied / units) };
}

/**
 * @param {Object} line
 * @param {number} line.listPrice - list price per unit (before any manual edit)
 * @param {number} line.rate - rate per unit after a rate edit (before the discount)
 * @param {number} line.qty
 * @param {number} line.discountPercentage - manual discount %, or 0
 * @param {number} line.discountAmount - manual discount for the line, or 0
 * @param {number} line.maxDiscount - Max Discount Percentage Allowed (0 = no limit)
 * @returns {string|null} the error to show, or null when allowed
 */
export function manualDiscountError({
	listPrice,
	rate,
	qty,
	discountPercentage,
	discountAmount,
	maxDiscount,
}) {
	const subtotal = (Number(rate) || 0) * (Number(qty) || 0);
	const discount =
		Number(discountPercentage) > 0
			? (subtotal * Number(discountPercentage)) / 100
			: Number(discountAmount) || 0;
	if (discount <= 0) return null;
	if (discount >= subtotal) {
		return __("Item discount must be less than 100%");
	}
	const listTotal = (Number(listPrice) || 0) * (Number(qty) || 0);
	const limit = Number(maxDiscount) || 0;
	if (limit > 0 && listTotal > 0) {
		const taken = Math.round(((listTotal - (subtotal - discount)) / listTotal) * 10000) / 100;
		if (taken > limit) {
			return __("Discount of {0}% exceeds maximum allowed discount of {1}%", [
				taken.toFixed(2),
				limit,
			]);
		}
	}
	return null;
}

/**
 * Manual invoice (header) discount, capped as the server caps it: Max Discount
 * Percentage Allowed (0 = no limit) of the total the header applies to, after the
 * line discounts, and never more than that total. Line and header discounts are
 * capped separately (one cap each).
 *
 * @param {Object} input
 * @param {number} input.value - what the cashier typed: a percentage or an amount
 * @param {boolean} input.isPercentage
 * @param {number} input.base - total before the invoice discount, after line discounts
 * @param {number} input.maxDiscount - Max Discount Percentage Allowed (0 = no limit)
 * @returns {{amount: number, value: number, limited: boolean}} the discount amount, the
 *   field's value after capping, and whether Max Discount Percentage Allowed cut it
 */
export function capInvoiceDiscount({ value, isPercentage, base, maxDiscount }) {
	const typed = Math.max(Number(value) || 0, 0);
	const total = Math.max(Number(base) || 0, 0);
	const limit = Number(maxDiscount) > 0 ? Math.min(Number(maxDiscount), 100) : 100;
	if (isPercentage) {
		const percentage = Math.min(typed, limit);
		return {
			amount: (total * percentage) / 100,
			value: percentage,
			limited: limit < 100 && typed > limit,
		};
	}
	const maxAmount = (total * limit) / 100;
	const amount = Math.min(typed, maxAmount);
	return { amount, value: amount, limited: limit < 100 && typed > maxAmount };
}
