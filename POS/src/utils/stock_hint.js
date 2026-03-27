export function formatStockQuantity(value) {
	const num = Number(value)
	if (!Number.isFinite(num)) return "0"
	if (Math.abs(num - Math.round(num)) < 0.0001) {
		return String(Math.round(num))
	}
	return String(Math.round(num * 10000) / 10000)
}

export function extractAvailableStock(item = {}, stockCheck = null) {
	const candidates = [
		stockCheck?.available_qty,
		stockCheck?.actual_qty,
		stockCheck?.stock_qty,
		stockCheck?.qty,
		item?.actual_qty,
		item?.stock_qty,
	]
	for (const candidate of candidates) {
		const num = Number(candidate)
		if (Number.isFinite(num)) return num
	}
	return 0
}

export function getStockHint(item = {}, stockCheck = null) {
	const availableQty = extractAvailableStock(item, stockCheck)
	const stockUom = item?.stock_uom || item?.uom || ""
	if (availableQty <= 0) {
		return stockUom ? `Only 0 ${stockUom} available` : "Out of stock"
	}
	return stockUom
		? `Only ${formatStockQuantity(availableQty)} ${stockUom} available`
		: `Only ${formatStockQuantity(availableQty)} available`
}
