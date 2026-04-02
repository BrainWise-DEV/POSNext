function normalizePolicyRow(row, fallbackStockUom = "") {
	const uom = row?.uom || row?.value || row?.name || ""
	if (!uom) return null

	return {
		uom,
		conversion_factor: Number(row?.conversion_factor || (uom === fallbackStockUom ? 1 : 1)) || 1,
		is_stock_uom: Boolean(row?.is_stock_uom || uom === fallbackStockUom),
		allow_for_selling:
			row?.allow_for_selling === undefined ? true : Boolean(row.allow_for_selling),
		allow_for_buying:
			row?.allow_for_buying === undefined ? true : Boolean(row.allow_for_buying),
	}
}

function dedupeRows(rows = []) {
	const seen = new Set()
	const out = []

	for (const row of rows) {
		if (!row?.uom || seen.has(row.uom)) continue
		seen.add(row.uom)
		out.push(row)
	}

	return out
}

function buildFallbackAllUoms(item = {}) {
	const rows = []

	if (item?.stock_uom) {
		rows.push(
			normalizePolicyRow(
				{
					uom: item.stock_uom,
					conversion_factor: 1,
					is_stock_uom: true,
					allow_for_selling: true,
					allow_for_buying: true,
				},
				item.stock_uom
			)
		)
	}

	if (Array.isArray(item?.item_uoms)) {
		for (const row of item.item_uoms) {
			rows.push(normalizePolicyRow(row, item.stock_uom))
		}
	}

	return dedupeRows(rows.filter(Boolean))
}

function resolveRawPolicy(item = {}, rawPolicy = null) {
	if (
		rawPolicy &&
		(typeof rawPolicy === "object") &&
		(Array.isArray(rawPolicy.all_uoms) || Array.isArray(rawPolicy.allowed_uoms) || rawPolicy.default_uom)
	) {
		return rawPolicy
	}

	if (
		item?.uom_policy &&
		(typeof item.uom_policy === "object") &&
		(Array.isArray(item.uom_policy.all_uoms) ||
			Array.isArray(item.uom_policy.allowed_uoms) ||
			item.uom_policy.default_uom)
	) {
		return item.uom_policy
	}

	if (
		item?._uom_policy &&
		(typeof item._uom_policy === "object") &&
		(Array.isArray(item._uom_policy.all_uoms) ||
			Array.isArray(item._uom_policy.allowed_uoms) ||
			item._uom_policy.default_uom)
	) {
		return item._uom_policy
	}

	return {}
}

export function getUOMPolicy(item = {}, rawPolicy = null) {
	const stockUom = item?.stock_uom || item?.uom || ""
	const resolvedRawPolicy = resolveRawPolicy(item, rawPolicy)

	const rawAllRows = Array.isArray(resolvedRawPolicy?.all_uoms)
		? resolvedRawPolicy.all_uoms
		: []

	const normalizedAllRows = dedupeRows(
		(rawAllRows.length ? rawAllRows : buildFallbackAllUoms(item))
			.map((row) => normalizePolicyRow(row, stockUom))
			.filter(Boolean)
	)

	let allowedRows = Array.isArray(resolvedRawPolicy?.allowed_uoms)
		? resolvedRawPolicy.allowed_uoms
				.map((row) => normalizePolicyRow(row, stockUom))
				.filter(Boolean)
		: normalizedAllRows.filter((row) => row.allow_for_selling)

	if (!allowedRows.length && normalizedAllRows.length) {
		allowedRows = normalizedAllRows.filter((row) => row.allow_for_selling)
	}

	if (!allowedRows.length && stockUom) {
		allowedRows = [
			normalizePolicyRow(
				{
					uom: stockUom,
					conversion_factor: 1,
					is_stock_uom: true,
					allow_for_selling: true,
					allow_for_buying: true,
				},
				stockUom
			),
		].filter(Boolean)
	}

	const defaultUom =
		resolvedRawPolicy?.default_uom ||
		item?.resolved_uom ||
		allowedRows.find((row) => row.is_stock_uom)?.uom ||
		allowedRows[0]?.uom ||
		stockUom ||
		item?.uom ||
		null

	return {
		all_uoms: normalizedAllRows,
		allowed_uoms: dedupeRows(allowedRows),
		default_uom: defaultUom,
	}
}