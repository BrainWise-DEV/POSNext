/**
 * The sale queued by an offline checkout (synced later through submit_invoice).
 *
 * @param {Object} args
 * @param {Object} args.cart - the POS cart store
 * @param {Object} args.shift - the POS shift store
 * @param {string|null} args.customer - the selected customer name
 * @param {Object} args.paymentData - what the payment dialog collected
 * @param {string|null} [args.editedFrom] - the queued offline sale this one replaces
 * @param {string|null} [args.idempotencyDoctype] - that key's doctype, when not an invoice
 * @param {string|null} [args.idempotencyKey] - the key of an online submit of this cart
 *   that got no answer (Ruling 139): the sync then returns that sale if it was made
 */
export function buildOfflineInvoiceData({
	cart,
	shift,
	customer,
	paymentData,
	editedFrom = null,
	idempotencyKey = null,
	idempotencyDoctype = null,
}) {
	const data = {
		pos_profile: cart.posProfile,
		posa_pos_opening_shift: cart.posOpeningShift,
		company: shift.profileCompany,
		customer: customer || shift.profileCustomer,
		// The same items as the online submit (rate, discounts, pricing_rules, coupon tags).
		items: cart.formatItemsForSubmission(cart.invoiceItems),
		payments: JSON.parse(JSON.stringify(cart.payments)),
		sales_team: JSON.parse(JSON.stringify(cart.salesTeam || [])),
		grand_total: cart.grandTotal,
		total_tax: cart.totalTax,
		total_discount: cart.totalDiscount,
		// The coupon and header discount the online submit sends: an order-level coupon's
		// discount lives only in the header.
		discount_amount: cart.additionalDiscount || 0,
		coupon_code: cart.couponCode || null,
		write_off_amount: paymentData.write_off_amount || 0,
		change_amount: paymentData.change_amount || 0,
		is_credit_sale: paymentData.is_credit_sale ? 1 : 0,
		receivable_account: paymentData.receivable_account || null,
		edited_from: editedFrom || null,
	};
	if (idempotencyKey) data.idempotency_key = idempotencyKey;
	// An order's key carried by this sale (Ruling 146 (c)): the server looks it up as one.
	if (idempotencyKey && idempotencyDoctype && idempotencyDoctype !== "Sales Invoice") {
		data.idempotency_doctype = idempotencyDoctype;
	}
	return data;
}
