/**
 * Distinct sellable units of an item, stock unit first.
 * item_uoms can repeat the stock unit, so units are deduped by `uom`.
 *
 * @param {Object} item - Item with stock_uom and optional item_uoms [{ uom, conversion_factor }]
 * @returns {Array<{uom: string, conversion_factor: number}>}
 */
export function getDistinctUoms(item) {
	const units = [{ uom: item?.stock_uom, conversion_factor: 1 }, ...(item?.item_uoms || [])];
	return units.filter((u, i) => u.uom && units.findIndex((x) => x.uom === u.uom) === i);
}
