export function toNumber(value, fallback = 0) {
	const num = Number(value)
	return Number.isFinite(num) ? num : fallback
}

export function toArray(value) {
	return Array.isArray(value) ? value : []
}

export function firstNonEmpty(...values) {
	for (const value of values) {
		if (value !== undefined && value !== null && value !== "") {
			return value
		}
	}
	return null
}

export function clonePlain(value) {
	if (value === undefined) return undefined
	return JSON.parse(JSON.stringify(value))
}