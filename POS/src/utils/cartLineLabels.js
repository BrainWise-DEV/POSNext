/**
 * What the cart says a line saves: "20% off", "1 free", "Coupon WELCOME10".
 * Pure functions (no stores), so the cart and its tests share them.
 */

function t(text, args) {
	const translate = globalThis.__;
	if (typeof translate === "function") return translate(text, args);
	if (!args) return text;
	return text.replace(/{(\d+)}/g, (match, n) => (args[n] !== undefined ? args[n] : match));
}

function num(value) {
	const parsed = Number.parseFloat(value);
	return Number.isFinite(parsed) ? parsed : 0;
}

/** The line's discount as a % of its list amount. */
export function lineDiscountPercent(item) {
	const pct = num(item?.discount_percentage);
	if (pct > 0) return pct;
	const discountAmount = num(item?.discount_amount);
	if (discountAmount <= 0) return 0;
	const qty = num(item?.quantity || item?.qty);
	const rate = num(item?.price_list_rate || item?.rate);
	const base = qty * rate;
	if (base <= 0) return 0;
	return (discountAmount / base) * 100;
}

/** A line's net amount: 0 stays 0 (100% discount), a missing amount is qty × rate. */
export function paymentLineAmount(item) {
	const amount = Number.parseFloat(item?.amount);
	if (Number.isFinite(amount)) return amount;
	return num(item?.qty ?? item?.quantity) * num(item?.rate ?? item?.price_list_rate);
}

/**
 * A paid line (not a free row) whose discount takes its whole list amount. The server
 * saves it as is_free_item; the cart line stays a paid line and is only labelled Free.
 */
export function isFullyDiscountedLine(item) {
	if (!item || item.is_free_item) return false;
	const listAmount = num(item.qty ?? item.quantity) * num(item.price_list_rate || item.rate);
	if (listAmount <= 0 || num(item.discount_amount) <= 0) return false;
	return Math.abs(paymentLineAmount(item)) < 0.005;
}

function isGiftSaving(item) {
	return ["free_item", "gwp"].includes(item?.discount_source);
}

/**
 * The line's saving title. A coupon names only what applies: a coupon that replaced
 * a promotion or F&F is the coupon alone; only a coupon stacked on a promotion
 * ("Add on top") names both (D-R2-05).
 */
export function lineSavingTitle(item) {
	// A paid line discounted to nothing (100% coupon or price rule) is free (D-R2-06).
	if (isFullyDiscountedLine(item)) return t("Free");
	if (item?.coupon_code) {
		const pre = num(item.pre_coupon_discount?.discount_percentage);
		return item.coupon_stacked && pre > 0
			? t("{0}% off + Coupon {1}", [pre.toFixed(0), item.coupon_code])
			: t("Coupon {0}", [item.coupon_code]);
	}
	if (isGiftSaving(item)) {
		const unit = num(item.price_list_rate || item.rate);
		const units = unit ? Math.round(num(item.discount_amount) / unit) : 0;
		if (units > 0) return t("{0} free", [units]);
	}
	return t("{0}% off", [Number(lineDiscountPercent(item)).toFixed(0)]);
}

/**
 * The cart footer's Subtotal and Grand Total (C1, Ruling 150). `lineTax` is the lines'
 * tax BEFORE the header discount: the discount already takes its tax share off the
 * total, so building the total from the reduced Tax row would undercount it
 * (UIT-O100: 280 + 42 − 100 = 222, not 280 + 28.96 − 100). Tax-inclusive: the
 * subtotal shown is net of that tax.
 */
export function cartDisplayTotals({ subtotal = 0, lineTax = 0, discount = 0, taxInclusive = false } = {}) {
	const gross = num(subtotal);
	const tax = num(lineTax);
	const shownSubtotal = taxInclusive ? gross - tax : gross;
	return { subtotal: shownSubtotal, grandTotal: shownSubtotal + tax - num(discount) };
}
