/**
 * What a POS return refunds, as the server books it (D-R2-16).
 *
 * The server refunds the return's `rounded_total or grand_total`. The return
 * rounds like its original invoice, and ERPNext rounds the return's negative
 * total. A refund that differs from it by more than the rounding is refused.
 */
import { invoiceRoundedTotal, roundCurrency } from "./currency";

/**
 * The refund for a return worth `returnValue` (sum of the returned rows, positive).
 * `original`: the original invoice's `disable_rounded_total` and
 * `smallest_currency_fraction_value`, from prepare_return_invoice.
 */
export function returnRefundAmount(returnValue, original) {
	const value = roundCurrency(Number(returnValue) || 0);
	return -invoiceRoundedTotal(-value, original) || 0;
}

/**
 * The refund capped at `refundable`: the cash still refundable on the original
 * after earlier returns (Ruling 147). No cap when it is not known.
 * `empties`: the return takes back everything left of a fully paid original, so
 * it refunds exactly the paid remainder, above its own rounded total if earlier
 * partial returns rounded down (Ruling 151).
 */
export function capRefund(refund, refundable, empties = false) {
	const amount = roundCurrency(Number(refund) || 0);
	if (refundable === undefined || refundable === null || refundable === "") return amount;
	const left = roundCurrency(Math.max(0, Number(refundable) || 0));
	return empties ? left : Math.min(amount, left);
}

/**
 * Whether the selected return quantities take back every paid row in full
 * (free rows carry no money and need not come back).
 */
export function emptiesOriginal(items) {
	const paid = items.filter((item) => Number(item.rate_with_tax || item.rate) > 0);
	return (
		paid.length > 0 &&
		paid.every((item) => item.selected && Number(item.return_qty) >= Number(item.remaining_qty))
	);
}

/**
 * Split `total` over refund rows in proportion to `weights`: what each original
 * payment row kept, net of change. The rounding remainder goes on the row with
 * the largest weight. With no weights, everything goes on the first row.
 */
export function splitRefund(total, weights) {
	const amount = roundCurrency(Number(total) || 0);
	const shares = weights.map((weight) => Math.max(0, Number(weight) || 0));
	const sum = shares.reduce((acc, weight) => acc + weight, 0);
	if (!shares.length) return [];
	if (sum <= 0) return shares.map((_, index) => (index === 0 ? amount : 0));

	const split = shares.map((weight) => roundCurrency((amount * weight) / sum));
	const largest = shares.indexOf(Math.max(...shares));
	const remainder = roundCurrency(amount - split.reduce((acc, value) => acc + value, 0));
	split[largest] = roundCurrency(split[largest] + remainder);
	return split;
}
