/**
 * How close the cart is to an offer, and what the offer gives, for the
 * cart's offers strip and the offers dialog.
 */

/**
 * @param {Object} offer - Offer with optional min_qty / min_amt
 * @param {{ qty?: number, amount?: number }} cart - Eligible qty and amount in the cart
 * @returns {null|{kind: "qty"|"amount", have: number, need: number, missing: number, percent: number}}
 *   null when the minimums are met or nothing in the cart counts toward them
 */
export function offerProgress(offer, { qty = 0, amount = 0 } = {}) {
	const minQty = Number(offer?.min_qty) || 0;
	const minAmt = Number(offer?.min_amt) || 0;
	const [kind, have, need] =
		minQty > qty ? ["qty", qty, minQty] : minAmt > amount ? ["amount", amount, minAmt] : [];
	if (!kind || have <= 0) return null;
	return { kind, have, need, missing: need - have, percent: Math.min((have / need) * 100, 100) };
}

/** What the customer gets, e.g. "20% off", "1 free", "Gift: Charger". */
export function offerBenefit(offer, formatCurrency) {
	if (offer?.offer === "Give Product") {
		return offer.same_item || !offer.free_item
			? __("{0} free", [offer.free_qty || 1])
			: __("Gift: {0}", [offer.free_item]);
	}
	if (Number(offer?.discount_percentage) > 0) {
		return __("{0}% off", [Number(offer.discount_percentage)]);
	}
	if (Number(offer?.discount_amount) > 0) {
		return __("{0} off", [formatCurrency(offer.discount_amount)]);
	}
	return __("Special price");
}

/** Label for ERPNext's raw offer type ("Give Product", "Item Price"). */
export function offerTypeLabel(type) {
	return { "Give Product": __("Free gift"), "Item Price": __("Price discount") }[type] || __("Discount");
}
