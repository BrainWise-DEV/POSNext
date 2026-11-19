import { getPrecision } from "@/utils/currency";

/**
 * Can the payment dialog complete the sale? Pure, so it is unit-testable.
 *
 * A sale whose total is 0.00 (a 100% coupon, only free rows) needs no payment
 * (D-14): ERPNext asks for a mode of payment only when grand_total > 0
 * (SalesInvoice.validate_pos_paid_amount), so it completes with none.
 *
 * @param {Object} state
 * @param {number} state.invoiceTotal     the invoice's grand total before rounding (zero-total test)
 * @param {number} state.remaining        what is still to collect (≥ 0)
 * @param {number} state.totalPaid
 * @param {number} state.entryCount       payment entries in the dialog
 * @param {boolean} [state.salesPersonValid]
 * @param {boolean} [state.customerOk]     a receivable mode has its customer
 * @param {boolean} [state.exactAmountValid]
 * @param {boolean} [state.receivableAccount] "Pay on Receivable Account" chosen (credit sale allowed)
 * @param {number} [state.receivableLimit] most that may be tendered with a receivable account
 * @param {boolean} [state.allowPartialPayment]
 * @param {boolean} [state.writeOffCovers]  write-off applied and covering the remainder
 * @param {number} [state.precision]       currency precision (default: the system's)
 * @returns {boolean}
 */
export function canCompletePayment({
	invoiceTotal = 0,
	remaining = 0,
	totalPaid = 0,
	entryCount = 0,
	salesPersonValid = true,
	customerOk = true,
	exactAmountValid = true,
	receivableAccount = false,
	receivableLimit = 0,
	allowPartialPayment = false,
	writeOffCovers = false,
	precision = undefined,
} = {}) {
	if (!salesPersonValid || !customerOk || !exactAmountValid) return false;
	if (isZeroTotal(invoiceTotal, precision)) return true;
	if (receivableAccount) return totalPaid <= receivableLimit + 0.01;
	if (allowPartialPayment) return totalPaid > 0 && entryCount > 0;
	if (writeOffCovers) return entryCount > 0;
	return remaining === 0 && entryCount > 0;
}

/** A zero invoice to the currency's precision (under half its smallest unit), never a return's negative total. */
export function isZeroTotal(total, precision = getPrecision().currency ?? 2) {
	const value = Number(total);
	return Number.isFinite(value) && Math.abs(value) < 10 ** -precision / 2;
}
