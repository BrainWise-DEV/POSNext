/**
 * Labels for the reasons nextend's sales approval gives for holding a line
 * (nextend/sales_approval/engine.py REASON_*). The cashier is told why, never
 * the HPP itself.
 */
export function approvalReasonLabel(reason) {
	if (reason === "hpp_unknown") return __("HPP belum diketahui (stok tanpa lot pembelian)");
	if (reason === "below_hpp") return __("Harga di bawah HPP");
	if (reason === "low_margin") return __("Margin di bawah minimum");
	return __("Perlu approval");
}
