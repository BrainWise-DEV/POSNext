const { BrowserWindow } = require("electron")

/**
 * Native Printing Module for Electron Desktop POS.
 *
 * Replaces QZ Tray with Electron's built-in printing capabilities.
 * Supports both thermal receipt printers and standard printers.
 */

/**
 * Get list of available printers.
 * @param {BrowserWindow} mainWindow
 * @returns {Promise<Array>}
 */
async function getAvailablePrinters(mainWindow) {
	if (!mainWindow) return []
	return mainWindow.webContents.getPrintersAsync()
}

/**
 * Print HTML content to a specific printer.
 * Creates a hidden window, loads the HTML, and sends to printer.
 *
 * @param {string} html - Receipt HTML content
 * @param {string} printerName - Target printer name (empty = default)
 * @param {Object} options - Print options
 * @param {boolean} options.silent - Skip print dialog (default: true)
 * @param {boolean} options.printBackground - Print background colors (default: true)
 * @param {number} options.copies - Number of copies (default: 1)
 * @param {Object} options.margins - Page margins
 * @returns {Promise<{success: boolean}>}
 */
async function printHTML(html, printerName = "", options = {}) {
	const printWindow = new BrowserWindow({
		show: false,
		webPreferences: {
			contextIsolation: true,
			nodeIntegration: false,
		},
	})

	try {
		// Load the receipt HTML
		await printWindow.loadURL(
			`data:text/html;charset=utf-8,${encodeURIComponent(html)}`
		)

		// Wait a moment for rendering
		await new Promise((resolve) => setTimeout(resolve, 500))

		return new Promise((resolve, reject) => {
			printWindow.webContents.print(
				{
					silent: options.silent !== false,
					printBackground: options.printBackground !== false,
					deviceName: printerName,
					copies: options.copies || 1,
					margins: options.margins || {
						marginType: "none",
					},
					pageSize: options.pageSize || {
						width: 80000, // 80mm in microns (receipt printer width)
						height: 297000, // Will auto-size based on content
					},
					...options,
				},
				(success, failureReason) => {
					printWindow.close()
					if (success) {
						resolve({ success: true })
					} else {
						reject(new Error(failureReason || "Print failed"))
					}
				},
			)
		})
	} catch (error) {
		printWindow.close()
		throw error
	}
}

/**
 * Generate receipt HTML from invoice data.
 * This is a basic template - can be customized per POS Profile print format.
 *
 * @param {Object} invoice - Invoice data
 * @param {Object} profile - POS Profile data
 * @returns {string} HTML string
 */
function generateReceiptHTML(invoice, profile) {
	const items = invoice.items || []
	const payments = invoice.payments || []

	const itemRows = items
		.map(
			(item) => `
		<tr>
			<td>${item.item_name || item.item_code}</td>
			<td style="text-align:center">${item.qty}</td>
			<td style="text-align:right">${item.rate?.toFixed(2)}</td>
			<td style="text-align:right">${item.amount?.toFixed(2)}</td>
		</tr>
	`,
		)
		.join("")

	const paymentRows = payments
		.map(
			(p) => `
		<tr>
			<td>${p.mode_of_payment}</td>
			<td style="text-align:right">${p.amount?.toFixed(2)}</td>
		</tr>
	`,
		)
		.join("")

	return `
		<!DOCTYPE html>
		<html>
		<head>
			<style>
				body { font-family: 'Courier New', monospace; font-size: 12px; width: 72mm; margin: 0 auto; padding: 5mm; }
				h2 { text-align: center; margin: 5px 0; }
				.info { text-align: center; font-size: 10px; color: #666; }
				table { width: 100%; border-collapse: collapse; margin: 8px 0; }
				th, td { padding: 2px 4px; font-size: 11px; }
				th { border-bottom: 1px dashed #000; text-align: left; }
				.divider { border-top: 1px dashed #000; margin: 5px 0; }
				.total { font-weight: bold; font-size: 14px; }
				.footer { text-align: center; font-size: 9px; margin-top: 10px; color: #666; }
			</style>
		</head>
		<body>
			<h2>${profile?.company || "POSNext"}</h2>
			<p class="info">${invoice.posting_date} ${invoice.posting_time || ""}</p>
			<p class="info">Invoice: ${invoice.name}</p>
			${invoice.customer_name ? `<p class="info">Customer: ${invoice.customer_name}</p>` : ""}

			<table>
				<thead>
					<tr><th>Item</th><th>Qty</th><th>Rate</th><th>Amount</th></tr>
				</thead>
				<tbody>${itemRows}</tbody>
			</table>

			<div class="divider"></div>

			<table>
				<tr><td>Subtotal</td><td style="text-align:right">${(invoice.net_total || 0).toFixed(2)}</td></tr>
				${invoice.discount_amount ? `<tr><td>Discount</td><td style="text-align:right">-${invoice.discount_amount.toFixed(2)}</td></tr>` : ""}
				<tr class="total"><td>Grand Total</td><td style="text-align:right">${(invoice.grand_total || 0).toFixed(2)}</td></tr>
			</table>

			<div class="divider"></div>

			<table>
				<thead><tr><th>Payment</th><th>Amount</th></tr></thead>
				<tbody>${paymentRows}</tbody>
			</table>

			${invoice.change_amount ? `<p><strong>Change: ${invoice.change_amount.toFixed(2)}</strong></p>` : ""}

			<p class="footer">Thank you for your purchase!</p>
			<p class="footer">Powered by POSNext Desktop</p>
		</body>
		</html>
	`
}

module.exports = {
	getAvailablePrinters,
	printHTML,
	generateReceiptHTML,
}
