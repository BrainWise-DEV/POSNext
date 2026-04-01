function asWarehouseName(value) {
	if (!value) return null;

	if (typeof value === "string") {
		const trimmed = value.trim();
		return trimmed || null;
	}

	if (typeof value === "object") {
		return (
			value.name ||
			value.warehouse ||
			value.value ||
			value.label ||
			null
		);
	}

	return null;
}

function normalizeWarehouse(value) {
	const name = asWarehouseName(value);
	if (!name) return null;

	return {
		name,
		warehouse: name,
		label: name,
		value: name,
	};
}

function dedupeWarehouses(list = []) {
	const map = new Map();

	for (const entry of list) {
		const normalized = normalizeWarehouse(entry);
		if (!normalized) continue;

		if (!map.has(normalized.name)) {
			map.set(normalized.name, normalized);
		}
	}

	return Array.from(map.values());
}

/**
 * Extract allowed warehouses from POS profile payload.
 *
 * Supports common shapes:
 * - profile.warehouse
 * - profile.allowed_warehouses
 * - profile.allowedWarehouses
 * - profile.pos_allowed_warehouse
 * - child rows like [{ warehouse: "Stores - S" }]
 */
export function getProfileAllowedWarehouses(profile) {
	if (!profile || typeof profile !== "object") return [];

	const rawList = [
		profile.warehouse,
		...(Array.isArray(profile.allowed_warehouses) ? profile.allowed_warehouses : []),
		...(Array.isArray(profile.allowedWarehouses) ? profile.allowedWarehouses : []),
		...(Array.isArray(profile.pos_allowed_warehouse) ? profile.pos_allowed_warehouse : []),
	];

	return dedupeWarehouses(rawList);
}

/**
 * Resolve the warehouse options that the POS UI should show.
 *
 * Rule for Phase 1:
 * - if profile exposes allowed warehouses, use only those
 * - otherwise fall back to the incoming options from core POSNext
 */
export function resolveWarehouseOptions({
	profile,
	availableWarehouses = [],
} = {}) {
	const allowed = getProfileAllowedWarehouses(profile);

	if (allowed.length) {
		return allowed;
	}

	return dedupeWarehouses(availableWarehouses);
}

/**
 * Check whether a warehouse is selectable under current profile rules.
 */
export function isWarehouseAllowed(warehouse, profile) {
	const name = asWarehouseName(warehouse);
	if (!name) return false;

	const allowed = getProfileAllowedWarehouses(profile);

	if (!allowed.length) {
		return true;
	}

	return allowed.some((entry) => entry.name === name);
}