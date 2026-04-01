import { firstNonEmpty, toArray } from "./shared"

export function normalizeAllowedUOMs(item = {}, policy = {}) {
	const allowed =
		toArray(policy.allowed_uoms).length > 0
			? toArray(policy.allowed_uoms)
			: toArray(item.uoms)

	return allowed
		.map((row) => {
			if (typeof row === "string") {
				return { uom: row }
			}
			return {
				...row,
				uom: row?.uom || row?.value || row?.name || null,
			}
		})
		.filter((row) => row.uom)
}

export function getDefaultUOM(item = {}, policy = {}) {
	return firstNonEmpty(
		policy.default_uom,
		item.uom,
		item.stock_uom,
		normalizeAllowedUOMs(item, policy)[0]?.uom,
	)
}

export function getUOMPolicy(item = {}, policy = {}) {
	const allowed_uoms = normalizeAllowedUOMs(item, policy)
	const default_uom = getDefaultUOM(item, policy)

	return {
		allowed_uoms,
		default_uom,
	}
}