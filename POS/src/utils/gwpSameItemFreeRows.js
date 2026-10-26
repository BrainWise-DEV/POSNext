/**
 * Same-SKU GWP free rows carve qty off the paid line and mark
 * `gwp_same_item_row: 1`. That qty must be restored before free rows are
 * dropped or rebuilt — otherwise the cart undercharges for scanned units.
 *
 * The flag is client-only (not in buildOfferEvaluationPayload), so this
 * restore is the only reconstruction path. Callers that remove free rows
 * must go through syncCartFreeItems / processFreeItems.
 */

function findPaidCartItem(items, itemCode, uom) {
	if (!itemCode) return null;
	const paid = items.filter((item) => !item.is_free_item && item.item_code === itemCode);
	if (!paid.length) return null;
	if (uom) {
		const matchedUom = paid.find((item) => (item.uom || item.stock_uom) === uom);
		if (matchedUom) return matchedUom;
	}
	return paid[0];
}

/**
 * Restore qty previously carved into same-SKU free rows (legacy carts), drop
 * all free rows, then rebuild free rows from `freeItems` as additional lines on
 * top of the paid quantity (never carved).
 *
 * @param {Array} items - Cart lines (mutates paid-line quantities in place)
 * @param {Array} freeItems - Free lines from offer response (optional `min_qty` of their rule), or [] to clear
 * @param {{ recalculateItem?: Function }} [opts]
 * @returns {Array} Next cart lines (paid + new free rows)
 */
export function syncCartFreeItems(items, freeItems, { recalculateItem } = {}) {
	const recalc = typeof recalculateItem === "function" ? recalculateItem : () => {};
	const cart = Array.isArray(items) ? items : [];

	for (const item of cart) {
		if (!item.is_free_item || Number(item.gwp_same_item_row) !== 1) continue;
		const freeQty = Number.parseFloat(item.quantity) || 0;
		if (freeQty <= 0) continue;
		const paid = findPaidCartItem(cart, item.item_code, item.uom || item.stock_uom);
		if (paid) {
			paid.quantity = (Number.parseFloat(paid.quantity) || 0) + freeQty;
			recalc(paid);
		}
	}

	for (const item of cart) {
		if (!item.is_free_item) {
			item.free_qty = 0;
		}
	}

	const next = cart.filter((item) => !item.is_free_item);

	if (!Array.isArray(freeItems) || freeItems.length === 0) {
		return next;
	}

	for (const freeItem of freeItems) {
		const freeQty = Number.parseFloat(freeItem.qty) || 0;
		if (freeQty <= 0) continue;

		const freeUom = freeItem.uom || freeItem.stock_uom;
		const cartItem = findPaidCartItem(next, freeItem.item_code, freeUom);

		// The server (posnext_promotions gwp.py) qualifies same-SKU GWP on paid qty
		// only and returns the gift as an extra free row ON TOP of the paid units
		// (buy 2 get 1: 2 paid → 2 paid + 1 free; 3 paid → 3 paid + 1 free).
		// Never carve the gift out of the paid line: doing so made a typed/+ qty
		// of 3 snap back to 2 paid + 1 free. Legacy carved rows (gwp_same_item_row
		// === 1) from older carts are still restored above.
		const carveFromPaid = false;

		const cf = freeItem.conversion_factor || cartItem?.conversion_factor || 1;
		next.push({
			item_code: freeItem.item_code,
			item_name: freeItem.item_name || cartItem?.item_name || freeItem.item_code,
			rate: 0,
			price_list_rate: 0,
			quantity: freeQty,
			discount_amount: 0,
			discount_percentage: 0,
			tax_amount: 0,
			amount: 0,
			stock_qty: 0,
			uom: cartItem?.uom || freeUom,
			stock_uom: cartItem?.stock_uom || freeItem.stock_uom || freeUom,
			conversion_factor: cf,
			is_free_item: 1,
			free_qty: freeQty,
			discount_source: freeItem.discount_source || (carveFromPaid ? "gwp" : "free_item"),
			gwp_same_item_row: carveFromPaid ? 1 : 0,
			pricing_rules: freeItem.pricing_rules || null,
			warehouse: freeItem.warehouse || cartItem?.warehouse,
			image: cartItem?.image || freeItem.image,
		});
	}

	return next;
}

/**
 * min_qty of the rule that produced a free line. `pricing_rules` may be a
 * string, a comma list or an array; falls back to the applied-offer entries so
 * a missing offers-store entry never silently disables the min_qty guard.
 */
export function resolveFreeItemMinQty(freeItem, availableOffers = [], appliedOffers = []) {
	const raw = freeItem?.pricing_rules;
	const codes = (Array.isArray(raw) ? raw : String(raw || "").split(","))
		.map((c) => String(c).trim())
		.filter(Boolean);
	let best;
	for (const code of codes) {
		const offer =
			(availableOffers || []).find((o) => o?.name === code) ||
			(appliedOffers || []).find((o) => o?.code === code)?.offer ||
			(appliedOffers || []).find((o) => o?.code === code);
		const minQty = Number.parseFloat(offer?.min_qty);
		if (Number.isFinite(minQty) && (best === undefined || minQty > best)) best = minQty;
	}
	return best;
}

/** Total units of a SKU across paid + free rows (scanned / stock demand). */
export function totalSkuQty(items, itemCode, uom) {
	return (items || [])
		.filter((item) => {
			if (item.item_code !== itemCode) return false;
			if (!uom) return true;
			return (item.uom || item.stock_uom) === uom;
		})
		.reduce((sum, item) => sum + (Number.parseFloat(item.quantity) || 0), 0);
}

/**
 * Offer-evaluation view of the cart: same order/length as `items`, but each
 * paid line carries back the qty carved into its same-SKU free rows
 * (`gwp_same_item_row: 1`). Those units were scanned/paid demand; leaving them
 * out makes min_qty checks see e.g. 1 instead of 2 after a 3→2 reduction, so
 * the offer is dropped and the restore then leaves 2 full-price units with no
 * gift. Does not mutate `items`.
 */
export function withCarvedQtyRestored(items) {
	const cart = Array.isArray(items) ? items : [];
	const view = cart.map((item) => ({ ...item }));
	const paidView = view.filter((item) => !item.is_free_item);
	for (const item of cart) {
		if (!item.is_free_item || Number(item.gwp_same_item_row) !== 1) continue;
		const freeQty = Number.parseFloat(item.quantity) || 0;
		if (freeQty <= 0) continue;
		const paid = findPaidCartItem(paidView, item.item_code, item.uom || item.stock_uom);
		if (paid) paid.quantity = (Number.parseFloat(paid.quantity) || 0) + freeQty;
	}
	return view;
}

function stampedFreeQty(item) {
	return item?.discount_source === "free_item" ? Number.parseFloat(item?.free_qty) || 0 : 0;
}

/**
 * Qty shown in a paid line's input. A same-SKU gift that the server stamps on
 * the paid line (discount_source "free_item" + free_qty) is NOT bundled into the
 * displayed number, so the displayed number is the paid qty.
 */
export function getDisplayQuantity(item) {
	const bundled = stampedFreeQty(item) > 0 ? 0 : Number.parseFloat(item?._bundledFreeQty) || 0;
	if (bundled > 0) {
		return (Number.parseFloat(item.quantity) || 0) + bundled;
	}
	return Number.parseFloat(item?.quantity) || 0;
}

/**
 * Inverse of getDisplayQuantity for a typed value. Must mirror it exactly:
 * previously a "free_item" line displayed its paid qty but the typed value had
 * free_qty subtracted, so typing 3 set 2 paid and typing 1 set 0 (ignored /
 * removed) — the offer never dropped from the keyboard path.
 */
export function resolvePaidQuantityFromDisplay(item, displayQty) {
	const bundled = stampedFreeQty(item) > 0 ? 0 : Number.parseFloat(item?._bundledFreeQty) || 0;
	if (bundled > 0) {
		return Math.max(0, displayQty - bundled);
	}
	return displayQty;
}
