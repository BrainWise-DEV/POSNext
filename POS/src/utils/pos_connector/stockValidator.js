export function buildStockHint({
	validation = {},
	stockUom = null,
	blockedTitle = "Insufficient stock",
	warningTitle = "Low stock",
	allowedNote = "Sale allowed",
} = {}) {
	if (!validation || validation.isAvailable) {
		return null
	}

	return {
		blocked: Boolean(validation.enforceStock),
		title: validation.enforceStock ? blockedTitle : warningTitle,
		note: validation.enforceStock ? "" : allowedNote,
		availableStock: validation.availableStock ?? 0,
		requiredStock: validation.requiredStock ?? 0,
		shortage: validation.shortage ?? 0,
		stockUom,
	}
}