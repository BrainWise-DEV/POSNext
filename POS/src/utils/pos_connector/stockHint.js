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

export function getStockDisplayState({
	item = {},
	selectedOption = null,
	quantity = 1,
	enforceStockValidation = false,
	validationResult = null,
} = {}) {
	if (!item || !selectedOption) return null

	const selectedUom = selectedOption?.uom || item?.uom || ""
	const stockUom = item?.stock_uom || selectedUom || ""

	if (validationResult?.reason === "uom_not_allowed") {
		return {
			type: "uom_blocked",
			title: "Not allowed for selling",
			note: selectedUom
				? `UOM "${selectedUom}" is not allowed for selling this item`
				: "This UOM is not allowed for selling this item",
			blocked: true,
			available: null,
			required: null,
			stockUom,
			panelClass: "bg-red-50 text-red-700 border border-red-200",
		}
	}

	const available = extractAvailableStock(item, validationResult?.stock)
	const conversionFactor = Number(selectedOption?.conversion_factor || 1)
	const qty = Number(quantity || 1) || 1
	const required = qty * conversionFactor

	if (required <= available) {
		return null
	}

	if (enforceStockValidation) {
		return {
			type: "insufficient_stock",
			title: "Insufficient stock",
			note: "",
			blocked: true,
			available,
			required,
			stockUom,
			panelClass: "bg-orange-50 text-orange-700 border border-orange-200",
		}
	}

	return {
		type: "low_stock",
		title: "Low stock",
		note: "Selling allowed (negative stock enabled)",
		blocked: false,
		available,
		required,
		stockUom,
		panelClass: "bg-yellow-50 text-yellow-700 border border-yellow-200",
	}
}
