/**
 * What the return dialog shows for an invoice (D-R4-09 d/e).
 */

/**
 * The amount the customer paid for the invoice, as the till collected it: payments less
 * change (288.00 for a 287.52 sale rounded to 288). An unpaid invoice shows what it is
 * for: its rounded total, else its grand total.
 */
export function returnListAmount(invoice) {
	const paid = (Number(invoice?.paid_amount) || 0) - (Number(invoice?.change_amount) || 0);
	if (paid > 0) return paid;
	return Number(invoice?.rounded_total) || Number(invoice?.grand_total) || 0;
}

/** A per-unit figure marked as one, so it is not read against the line's multi-unit total. */
export function perUnitLabel(formattedAmount, uom) {
	return uom ? `${formattedAmount}/${uom}` : formattedAmount;
}
