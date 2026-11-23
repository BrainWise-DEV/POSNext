import { roundCurrency } from "@/utils/currency";

/**
 * The total of a held cart as the cart showed it. A draft held since review M8 carries
 * the cart's grand total, header discount included; an older one is summed: each line's
 * net amount after offers and coupons plus its tax (D-R4-09 a: a held F&F cart showed
 * its net 134.00, not 154.00), or rate × qty without line amounts.
 */
export function heldCartTotal(draft) {
	const total = draft?.grand_total;
	if (typeof total === "number" && Number.isFinite(total)) return roundCurrency(total);
	return draftTotal(draft?.items);
}

export function draftTotal(items) {
	if (!items || items.length === 0) return 0;
	return roundCurrency(
		items.reduce((sum, item) => {
			if (typeof item.amount === "number") {
				return sum + roundCurrency(item.amount) + roundCurrency(Number(item.tax_amount) || 0);
			}
			const qty = item.quantity || item.qty || 1;
			return sum + roundCurrency(qty * roundCurrency(item.rate || 0));
		}, 0)
	);
}
