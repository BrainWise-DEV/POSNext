import { getPrecision, roundFloat } from "@/utils/currency"

const DEFAULT_FLOAT_PRECISION = 3

export function getReturnQuantityPrecision() {
	const precision = Number.parseInt(getPrecision().float, 10)
	return Number.isFinite(precision)
		? Math.max(0, precision)
		: DEFAULT_FLOAT_PRECISION
}

export function getMinReturnQuantity() {
	const precision = getReturnQuantityPrecision()
	if (precision === 0) return 1
	return Number((1 / 10 ** precision).toFixed(precision))
}

export function getReturnQuantityStep() {
	return getMinReturnQuantity()
}

export function roundReturnQuantity(quantity) {
	return roundFloat(Number(quantity) || 0)
}

export function formatReturnQuantity(quantity) {
	const roundedQuantity = roundReturnQuantity(quantity)
	return Number.isFinite(roundedQuantity) ? String(roundedQuantity) : "0"
}

export function clampReturnQuantity(quantity, maxQuantity) {
	const roundedMaxQuantity = roundReturnQuantity(maxQuantity)
	const minQuantity = getMinReturnQuantity()

	if (roundedMaxQuantity <= minQuantity) {
		return roundedMaxQuantity
	}

	const roundedQuantity = roundReturnQuantity(quantity)
	return Math.max(minQuantity, Math.min(roundedQuantity, roundedMaxQuantity))
}
