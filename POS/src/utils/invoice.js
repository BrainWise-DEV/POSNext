/**
 * Invoice utility functions
 * Common helpers for invoice-related operations across the application
 */

/**
 * Get the appropriate CSS classes for invoice status badge
 * @param {Object} invoice - Invoice object with status and docstatus fields
 * @returns {string} Tailwind CSS classes for the status badge
 */
export function getInvoiceStatusColor(invoice) {
	const status = invoice.status?.toLowerCase();

	// Red for overdue, cancelled
	if (status === "overdue" || invoice.docstatus === 2) {
		return "bg-red-100 text-red-800";
	}

	// Orange for partly paid (partial payment received)
	if (status === "partly paid" || status === "partially paid") {
		return "bg-orange-100 text-orange-800";
	}

	// Yellow for unpaid
	if (status === "unpaid") {
		return "bg-yellow-100 text-yellow-800";
	}

	// Blue for credit note issued
	if (status === "credit note issued") {
		return "bg-blue-100 text-blue-800";
	}

	// Green for paid, submitted
	if (status === "paid" || invoice.docstatus === 1) {
		return "bg-green-100 text-green-800";
	}

	// Gray for draft and others
	return "bg-gray-100 text-gray-800";
}

/**
 * Get status color theme name for use with Badge component
 * @param {string} status - Invoice status string
 * @returns {string} Theme name (red, yellow, blue, green, gray)
 */
export function getInvoiceStatusTheme(status) {
	const statusLower = status?.toLowerCase();

	if (statusLower === "overdue" || statusLower === "cancelled") {
		return "red";
	}

	if (statusLower === "partly paid" || statusLower === "partially paid") {
		return "orange";
	}

	if (statusLower === "unpaid") {
		return "yellow";
	}

	if (statusLower === "credit note issued") {
		return "blue";
	}

	if (statusLower === "paid") {
		return "green";
	}

	return "gray";
}

/**
 * Normalize validate_coupon API responses from frappe-ui call().
 * Success payloads include both `valid: true` and `message: "Coupon applied successfully"`,
 * so `result?.message || result` would incorrectly treat the string as the payload.
 * @param {*} raw
 * @returns {object|null}
 */
export function unwrapCouponValidation(raw) {
	if (!raw) return null;
	if (raw.valid !== undefined) return raw;
	if (raw.message?.valid !== undefined) return raw.message;
	if (typeof raw.message === "object" && raw.message) return raw.message;
	if (typeof raw.message === "string") return { valid: false, message: raw.message };
	return raw;
}

/**
 * Cart rows in the shape validate_coupon expects.
 * Lines already carrying the coupon send their pre-coupon (offer) discount,
 * so the server does not treat the coupon's own discount as the line's base.
 * @param {Array} items - cart invoice items
 * @returns {Array}
 */
export function buildCouponItemsSnapshot(items) {
	return (items || []).map((item, index) => {
		let discountPercentage = item.discount_percentage || 0;
		let discountAmount = item.discount_amount || 0;
		let alreadyDiscounted = item.is_already_discounted || 0;
		let discountSource = item.discount_source || "";
		if (item.coupon_code) {
			const prePct = Number.parseFloat(item.pre_coupon_discount_percentage);
			const preAmt = Number.parseFloat(item.pre_coupon_discount_amount);
			discountPercentage = prePct > 0 ? prePct : 0;
			discountAmount = prePct > 0 ? 0 : preAmt > 0 ? preAmt : 0;
			// No offer under the coupon: drop flags apply_offers stamped for the coupon's own discount
			if (!discountPercentage && !discountAmount) {
				alreadyDiscounted = 0;
				discountSource = "";
			}
		}

		return {
			item_code: item.item_code,
			item_name: item.item_name,
			brand: item.brand || "",
			item_group: item.item_group || "",
			qty: item.quantity || item.qty || 0,
			quantity: item.quantity || item.qty || 0,
			rate: item.rate || 0,
			price_list_rate: item.price_list_rate || item.rate || 0,
			amount: item.amount || 0,
			discount_percentage: discountPercentage,
			discount_amount: discountAmount,
			pricing_rules: item.pricing_rules || null,
			is_free_item: item.is_free_item || 0,
			is_already_discounted: alreadyDiscounted,
			discount_source: discountSource,
			coupon_code: item.coupon_code || "",
			idx: index + 1,
			name: item.name || null,
		};
	});
}
