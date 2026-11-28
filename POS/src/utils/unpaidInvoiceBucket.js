/**
 * Bucket for one invoice in the Unpaid tab, so the filter chips partition it:
 * overdue first (ERPNext marks an overdue partly-paid invoice "Overdue"), then
 * partly paid, else unpaid. "... and Discounted" statuses fall in the same buckets.
 *
 * @param {Object} invoice - Row with status and paid_amount
 * @returns {"overdue"|"partial"|"unpaid"} The one bucket the invoice belongs to
 */
export function unpaidInvoiceBucket(invoice) {
	const status = invoice?.status || "";
	if (status.startsWith("Overdue")) return "overdue";
	if (status.startsWith("Partly Paid") || Number(invoice?.paid_amount) > 0) return "partial";
	return "unpaid";
}
