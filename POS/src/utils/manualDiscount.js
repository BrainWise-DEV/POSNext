/**
 * Manual line discount limits (Edit Item dialog), as the server enforces them:
 * a cashier's discount stays below 100% of the line (a gift is an offer, never a
 * manual 100%), and Max Discount Percentage Allowed caps the whole reduction
 * from list price (rate edit plus discount). 0 = no limit.
 */

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
