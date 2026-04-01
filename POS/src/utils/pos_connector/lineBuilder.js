export function buildLine({
	item,
	qty,
	uom,
	conversion_factor,
	rate,
	discount_amount = 0,
	stockResult = {},
}) {
	const net_rate = rate - discount_amount
	const line_total = net_rate * qty

	return {
		ok: true,
		item,
		qty,
		uom,
		conversion_factor,

		pricing: {
			rate,
			discount_amount,
			net_rate,
			line_total,
		},

		stock: stockResult,

		ui_flags: {
			uom_locked: item?._uom_locked || false,
			stock_blocked: !stockResult?.available,
			discount_locked: false,
		},
	}
}