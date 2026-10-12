/**
 * Recognise an SPG order (nextend POS Order) in scanned or typed input.
 *
 * The order slip's QR holds the whole order as compact JSON (see
 * nextend.pos_order.build_qr_payload) so an offline cashier can still load
 * it; the order number printed on the slip can be typed in while online.
 */

const ORDER_NAME = /^SPO-\d{6}-\d+$/i;

/**
 * @param {string} text - Scanned barcode / typed search text
 * @returns {{ name: string, payload: Object|null } | null}
 */
export function parsePosOrderCode(text) {
	const value = (text || "").trim();
	if (ORDER_NAME.test(value)) {
		return { name: value.toUpperCase(), payload: null };
	}
	if (!value.startsWith("{")) return null;

	try {
		const payload = JSON.parse(value);
		if (payload?.v === 1 && ORDER_NAME.test(payload.o || "") && Array.isArray(payload.i)) {
			return { name: payload.o, payload };
		}
	} catch {
		// Not JSON - an ordinary barcode
	}
	return null;
}

/**
 * Expand a QR payload into the shape of a POS Order (as returned by
 * nextend.pos_order.get_order). Row columns follow build_qr_payload; trailing
 * empty columns are omitted there. `k` is the address of an order the SPG
 * marked Dikirim, `kc` the note for the driver.
 */
export function orderFromQrPayload(payload) {
	return {
		name: payload.o,
		status: "Pending",
		pos_opening_shift: payload.sh,
		sales_person: payload.sp,
		discount_amount: payload.d || 0,
		coupon_code: payload.c || null,
		dikirim: payload.k ? 1 : 0,
		alamat_kirim: payload.k || "",
		catatan_kirim: payload.kc || "",
		items: payload.i.map((r) => ({
			item_code: r[0],
			warehouse: payload.w[r[1]],
			qty: r[2],
			uom: r[3],
			rate: r[4] || 0,
			price_list_rate: r[5] ?? r[4] ?? 0,
			discount_amount: r[6] || 0,
			discount_percentage: r[7] || 0,
			conversion_factor: r[8] || 1,
			is_free_item: r[9] || 0,
			addon_item: r[10] || null,
			addon_key: r[11] || null,
			addon_parent_key: r[12] || null,
			keterangan: r[13] || "",
			addon_group: r[14] || null,
		})),
	};
}
