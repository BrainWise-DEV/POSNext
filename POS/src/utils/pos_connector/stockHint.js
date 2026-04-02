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


export function getUOMPolicy(item = {}, rawPolicy = {}) {
	const stockUom = item?.stock_uom || item?.uom || ""

	const rawAllRows = Array.isArray(rawPolicy?.all_uoms) ? rawPolicy.all_uoms : []
	const normalizedAllRows = dedupeRows(
		(rawAllRows.length ? rawAllRows : buildFallbackAllUoms(item))
			.map((row) => normalizePolicyRow(row, stockUom))
			.filter(Boolean)
	)

	let allowedRows = Array.isArray(rawPolicy?.allowed_uoms)
		? rawPolicy.allowed_uoms
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
		rawPolicy?.default_uom ||
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