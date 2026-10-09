/**
 * UOM pricing lock helpers.
 *
 * Changing UOM must not fetch a fresh price-list rate when the line is
 * promotion-owned (free/GWP) or already under a locked promo / manual rate.
 * Those paths would otherwise bypass the same free/promo pricing lock as
 * rate editing.
 */

const PROMO_DISCOUNT_SOURCES = new Set([
	"item_level_promotion",
	"accumulative_promotion",
]);

/**
 * Free / GWP rows are wholly owned by the promotion engine.
 * @param {Object|null|undefined} item
 * @returns {boolean}
 */
export function isFreePromoRow(item) {
	return Boolean(item?.is_free_item || item?._isStandaloneFreeRow);
}

/**
 * Whether a UOM change must preserve (scale) the current rate instead of
 * replacing it from the price list.
 * @param {Object|null|undefined} item
 * @returns {boolean}
 */
export function shouldPreserveRateOnUomChange(item) {
	if (!item) return false;
	if (isFreePromoRow(item)) return true;
	if (item.is_rate_manually_edited === 1 || item.is_rate_manually_edited === true) {
		return true;
	}
	return PROMO_DISCOUNT_SOURCES.has(item.discount_source);
}

/**
 * Scale a unit rate from one conversion factor to another.
 * @param {number} rate
 * @param {number} fromConversion
 * @param {number} toConversion
 * @returns {number}
 */
export function scaleRateForUomChange(rate, fromConversion, toConversion) {
	const from = Number(fromConversion) || 1;
	const to = Number(toConversion) || 1;
	return ((Number(rate) || 0) / from) * to;
}
