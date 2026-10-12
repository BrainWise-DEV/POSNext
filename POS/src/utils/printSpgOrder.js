/**
 * Order slip for an SPG order (nextend POS Order): the customer carries it to
 * the cashier, who scans the QR. The QR SVG comes from the server
 * (nextend.pos_order) and holds the whole order, so an offline cashier can
 * still load it.
 *
 * Printed through the browser print dialog - on Android a Bluetooth thermal
 * printer is reached through a print service app (e.g. RawBT).
 *
 * The window must be opened inside the click handler, before awaiting the
 * server: a window.open after an await is treated as an unrequested popup and
 * blocked. Open it with openSpgOrderSlipWindow() first, fill it once the order
 * arrives.
 */

import { formatCurrency } from "@/utils/currency";

function escapeHtml(value) {
	return String(value ?? "")
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;");
}

export function buildSpgOrderSlipHTML(order, currency) {
	// Each row says where it is taken from once any stock comes from outside
	// the toko warehouse (the order splits a line toko first, then the rest)
	const showWarehouse = (order.items || []).some(
		(item) => !item.addon_parent_key && item.warehouse !== order.store_warehouse
	);
	const itemsHtml = (order.items || [])
		.map((item) => {
			if (item.addon_parent_key) {
				return `
				<div class="row addon">
					<span>+ ${escapeHtml(item.addon_item ? item.item_name || item.addon_item : item.addon_group)}</span>
					<span>${formatCurrency(item.amount || 0, currency)}</span>
				</div>`;
			}
			return `
				<div class="item">${escapeHtml(item.item_name || item.item_code)}</div>
				<div class="row">
					<span>${item.qty} ${escapeHtml(item.uom)} x ${formatCurrency(item.rate || 0, currency)}</span>
					<span>${formatCurrency(item.amount || 0, currency)}</span>
				</div>${
					showWarehouse
						? `<div class="wh">${__("Ambil di")}: ${escapeHtml(
								item.warehouse === order.store_warehouse
									? __("Toko")
									: item.warehouse
						  )}</div>`
						: ""
				}`;
		})
		.join("");

	const discount = Number.parseFloat(order.discount_amount) || 0;

	return `<!DOCTYPE html>
<html>
<head>
	<meta charset="utf-8">
	<title>${escapeHtml(order.name)}</title>
	<style>
		@page { margin: 0; }
		body { font-family: monospace; font-size: 12px; width: 58mm; margin: 0 auto; padding: 4mm 2mm; color: #000; }
		.center { text-align: center; }
		.title { font-size: 14px; font-weight: bold; }
		.order-no { font-size: 18px; font-weight: bold; letter-spacing: 1px; margin: 4px 0; }
		.row { display: flex; justify-content: space-between; gap: 4px; }
		.addon { padding-left: 12px; }
		.item { margin-top: 4px; }
		.wh { font-size: 11px; padding-left: 8px; }
		.sep { border-top: 1px dashed #000; margin: 6px 0; }
		.total { font-weight: bold; font-size: 14px; }
		.qr svg { width: 100%; height: auto; }
		.note { font-size: 11px; margin-top: 4px; }
	</style>
</head>
<body>
	<div class="center title">${__("PESANAN")}</div>
	<div class="center order-no">${escapeHtml(order.name)}</div>
	<div class="center">${escapeHtml(order.pos_profile)}</div>
	<div class="sep"></div>
	<div class="row"><span>${__("SPG")}</span><span>${escapeHtml(
		order.spg_name || order.spg_user
	)}</span></div>
	<div class="row"><span>${__("Waktu")}</span><span>${escapeHtml(
		String(order.creation || "").slice(0, 16)
	)}</span></div>
	<div class="sep"></div>
	${itemsHtml}
	<div class="sep"></div>
	${
		discount
			? `<div class="row"><span>${__("Diskon")}</span><span>-${formatCurrency(
					discount,
					currency
			  )}</span></div>`
			: ""
	}
	<div class="row total"><span>${__("TOTAL")}</span><span>${formatCurrency(
		order.grand_total || 0,
		currency
	)}</span></div>
	<div class="sep"></div>
	<div class="qr">${order.qr_svg || ""}</div>
	<div class="center note">${__("Bawa struk ini ke kasir untuk pembayaran")}</div>
</body>
</html>`;
}

/** Open the slip window from a click handler; null when the browser blocks it. */
export function openSpgOrderSlipWindow() {
	const printWindow = window.open("", "_blank", "width=350,height=600");
	printWindow?.document.write(
		`<p style="font-family: monospace">${__("Menyiapkan struk...")}</p>`
	);
	return printWindow;
}

export function printSpgOrderSlip(order, currency, printWindow = openSpgOrderSlipWindow()) {
	if (!printWindow || printWindow.closed) {
		throw new Error(__("Popup blocked — check your browser settings."));
	}
	printWindow.document.open();
	printWindow.document.write(buildSpgOrderSlipHTML(order, currency));
	printWindow.document.close();
	// The slip has no external resources; onload is unreliable on a reused window
	setTimeout(() => printWindow.print(), 250);
}
