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
 * Restore qty previously carved into same-SKU free rows, drop all free rows,
 * then rebuild free rows from `freeItems` (carving again when same-SKU).
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

		// Same SKU (GWP buy 2 get 1): split scanned units while the paid rest still meets
		// min_qty. Qty 3 → 2 paid + 1 free; qty 2 → 2 paid + 1 free added on top.
		const paidQty = cartItem ? Number.parseFloat(cartItem.quantity) || 0 : 0;
		const minQty = Number.parseFloat(freeItem.min_qty) || 0;
		const carveFromPaid = Boolean(cartItem && paidQty > freeQty && paidQty - freeQty >= minQty);
		if (carveFromPaid) {
			cartItem.quantity = paidQty - freeQty;
			recalc(cartItem);
		}

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
 * Display order for the cart: each free row right after the paid line that
 * earned it (same SKU and unit, else the line carrying its pricing rule).
 * Paid lines get `_bundledFreeQty`, the same-item gift qty carved out of them.
 *
 * @param {Array} items - Cart lines in display order
 * @returns {Array} Copies of the lines; nested gifts marked `_giftOf`, other free rows last
 */
export function nestFreeRows(items) {
	const rows = items || [];
	const paid = rows.filter((item) => !item.is_free_item);
	const rulesOf = (item) =>
		Array.isArray(item.pricing_rules)
			? item.pricing_rules
			: String(item.pricing_rules || "").split(",").map((r) => r.trim());
	const parentOf = (gift) =>
		findPaidCartItem(paid, gift.item_code, gift.uom || gift.stock_uom) ||
		paid.find((item) => gift.pricing_rules && rulesOf(item).includes(gift.pricing_rules));
	const gifts = rows
		.filter((item) => item.is_free_item)
		.map((gift) => ({ gift, parent: parentOf(gift) }));
	const giftRow = (gift, parent) => ({
		...gift,
		_isStandaloneFreeRow: true,
		_giftOf: parent ? `${parent.item_code}-${parent.uom || ""}` : null,
	});

	return [
		...paid.flatMap((item) => {
			const own = gifts.filter((g) => g.parent === item).map((g) => g.gift);
			const bundled = totalSkuQty(
				own.filter((g) => Number(g.gwp_same_item_row) === 1),
				item.item_code
			);
			return [{ ...item, _bundledFreeQty: bundled }, ...own.map((g) => giftRow(g, item))];
		}),
		...gifts.filter((g) => !g.parent).map((g) => giftRow(g.gift, null)),
	];
}
