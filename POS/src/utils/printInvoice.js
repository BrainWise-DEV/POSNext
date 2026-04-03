import { call } from "@/utils/apiWrapper"
import { logger } from "@/utils/logger"
import { printHTML as qzPrintHTML } from "@/utils/qzTray"

const log = logger.create("PrintInvoice")

const DEFAULT_PRINT_FORMAT = "POS Next Receipt"

// ============================================================================
// Shared helpers
// ============================================================================

function formatCurrency(amount) {
	return Number.parseFloat(amount || 0).toFixed(2)
}

/**
 * Resolve print format & letterhead from a POS Profile.
 * Returns defaults when the profile lookup fails so callers always get a value.
 */
async function resolvePrintSettings(posProfile, printFormat, letterhead) {
	if (printFormat) return { printFormat, letterhead }

	if (posProfile) {
		try {
			const doc = await call("frappe.client.get", {
				doctype: "POS Profile",
				name: posProfile,
			})
			if (doc) {
				return {
					printFormat: doc.print_format || DEFAULT_PRINT_FORMAT,
					letterhead: letterhead || doc.letter_head || null,
				}
			}
		} catch (err) {
			log.warn("Could not fetch POS Profile print settings:", err)
		}
	}

	return { printFormat: DEFAULT_PRINT_FORMAT, letterhead }
}

// ============================================================================
// Browser printing (opens /printview in a new window)
// ============================================================================

/**
 * Open Frappe's /printview in a new browser window.
 * The page includes trigger_print=1 so the OS print dialog appears automatically.
 * Falls back to the hardcoded receipt template if the popup is blocked.
 */
export async function printInvoice(invoiceData, printFormat = null, letterhead = null) {
	try {
		if (!invoiceData?.name) throw new Error("Invalid invoice data")

		const doctype = invoiceData.doctype || "Sales Invoice"
		const format = printFormat || DEFAULT_PRINT_FORMAT

		const params = new URLSearchParams({
			doctype,
			name: invoiceData.name,
			format,
			no_letterhead: letterhead ? 0 : 1,
			_lang: "en",
			trigger_print: 1,
			_t: Date.now(),
		})
		if (letterhead) params.append("letterhead", letterhead)

		const printWindow = window.open(`/printview?${params}`, "_blank", "width=800,height=600")
		if (!printWindow) {
			throw new Error("Popup blocked — check your browser settings.")
		}
		return true
	} catch (error) {
		log.error("Browser print failed:", error)
		return printInvoiceCustom(invoiceData)
	}
}

/**
 * Fetch an invoice by name, resolve its POS Profile print settings,
 * then open the browser print window.
 */
export async function printInvoiceByName(invoiceName, printFormat = null, letterhead = null) {
	const invoiceDoc = await call("pos_next.api.invoices.get_invoice", {
		invoice_name: invoiceName,
	})
	if (!invoiceDoc) throw new Error("Invoice not found")

	const settings = await resolvePrintSettings(invoiceDoc.pos_profile, printFormat, letterhead)
	return printInvoice(invoiceDoc, settings.printFormat, settings.letterhead)
}

// ============================================================================
// Silent printing (QZ Tray — no browser dialog)
// ============================================================================

/**
 * Fetch the server-rendered print HTML and send it to a thermal printer
 * via QZ Tray. Uses Frappe's get_html_and_style API which returns the
 * print format HTML + its inline styles (standard.css, print style, custom CSS).
 * Note: print.bundle.css (Bootstrap grid/tables) is NOT included — print
 * formats that rely on Bootstrap layout classes may render differently.
 * Paper size and margins are controlled by the QZ Tray config in qzTray.js.
 */
export async function silentPrintInvoice(invoiceName, printFormat = null) {
	const format = printFormat || DEFAULT_PRINT_FORMAT

	const result = await call("frappe.www.printview.get_html_and_style", {
		doc: "Sales Invoice",
		name: invoiceName,
		print_format: format,
		no_letterhead: 1,
	})

	const html = result?.html || result?.message?.html
	const style = result?.style || result?.message?.style || ""
	if (!html) throw new Error("Failed to get print HTML from server")

	const fullHTML = `<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>${style}</style></head>
<body>${html}</body>
</html>`

	await qzPrintHTML(fullHTML)
	log.info(`Silent print sent for ${invoiceName}`)
	return true
}

/**
 * Try silent print, fall back to browser print on failure.
 * silentPrintInvoice → qzPrintHTML → connect() handles auto-reconnect
 * internally, so no separate connection logic is needed here.
 */
export async function printWithSilentFallback(invoiceData, printFormat = null) {
	const invoiceName = invoiceData?.name
	if (!invoiceName) throw new Error("Invalid invoice data — missing name")

	try {
		await silentPrintInvoice(invoiceName, printFormat)
		return { method: "silent", success: true }
	} catch (err) {
		log.warn("Silent print failed, falling back to browser:", err?.message || err)
	}

	try {
		await printInvoiceByName(invoiceName, printFormat)
		return { method: "browser", success: true }
	} catch (err) {
		log.error("Browser print fallback also failed:", err)
		return { method: "browser", success: false }
	}
}

// ============================================================================
// Hardcoded receipt fallback (used only when /printview popup is blocked)
// ============================================================================

/**
 * Last-resort receipt renderer. Builds a complete HTML document from the
 * invoice data and writes it into a new window. Only triggered when the
 * browser blocks the /printview popup.
 */
export function printInvoiceCustom(invoiceData) {
	const printWindow = window.open("", "_blank", "width=350,height=600")

	const printContent = `
		<!DOCTYPE html>
		<html>
		<head>
			<meta charset="UTF-8">
			<title>${__("Invoice - {0}", [invoiceData.name])}</title>
			<style>
				* { margin: 0; padding: 0; box-sizing: border-box; }
				body {
					font-family: 'Courier New', monospace;
					padding: 10px; width: 80mm; margin: 0; max-width: 80mm;
					font-weight: bold; color: black;
				}
				.receipt { width: 100%; }
				.header { text-align: center; margin-bottom: 20px; border-bottom: 2px dashed #000; padding-bottom: 10px; }
				.company-name { font-size: 18px; font-weight: bold; margin-bottom: 5px; }
				.invoice-info { margin-bottom: 15px; font-size: 12px; }
				.invoice-info div { display: flex; justify-content: space-between; margin-bottom: 3px; }
				.partial-status { color: #000; font-weight: bold; margin-bottom: 5px; }
				.items-table { width: 100%; margin-bottom: 15px; border-top: 1px dashed #000; border-bottom: 1px dashed #000; padding: 10px 0; }
				.item-row { margin-bottom: 10px; font-size: 12px; }
				.item-name { font-weight: bold; margin-bottom: 3px; }
				.item-details { display: flex; justify-content: space-between; font-size: 11px; }
				.item-discount { display: flex; justify-content: space-between; font-size: 10px; margin-top: 2px; }
				.item-serials { font-size: 9px; margin-top: 3px; padding: 3px 5px; border: 1px dashed #000; border-radius: 2px; }
				.item-serials-label { font-weight: bold; margin-bottom: 2px; }
				.item-serials-list { word-break: break-all; }
				.totals { margin-top: 15px; border-top: 1px dashed #000; padding-top: 10px; }
				.total-row { display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 12px; }
				.grand-total { font-size: 16px; font-weight: bold; border-top: 2px solid #000; padding-top: 10px; margin-top: 10px; }
				.payments { margin-top: 15px; border-top: 1px dashed #000; padding-top: 10px; }
				.payment-row { display: flex; justify-content: space-between; margin-bottom: 3px; font-size: 11px; }
				.total-paid { font-weight: bold; border-top: 1px solid #000; padding-top: 5px; margin-top: 5px; }
				.outstanding-row {
					display: flex; justify-content: space-between; font-size: 13px; font-weight: bold;
					border: 1px solid #000; padding: 8px; margin-top: 8px; border-radius: 4px;
				}
				.footer { text-align: center; margin-top: 20px; padding-top: 10px; border-top: 2px dashed #000; font-size: 11px; }
				@media print {
					@page { size: 80mm auto; margin: 0; }
					body { width: 80mm; padding: 5mm; margin: 0; }
					.no-print { display: none; }
				}
			</style>
		</head>
		<body>
			<div class="receipt">
				<div class="header">
					<div class="company-name">${invoiceData.company || "POS Next"}</div>
					<div style="font-size: 12px;">${invoiceData.header || __("TAX INVOICE")}</div>
				</div>

				<div class="invoice-info">
					<div><span>${__("Invoice #:")}</span><span><strong>${invoiceData.name}</strong></span></div>
					<div><span>${__("Date:")}</span><span>${new Date(invoiceData.posting_date || Date.now()).toLocaleString()}</span></div>
					${invoiceData.customer_name ? `<div><span>${__("Customer:")}</span><span>${invoiceData.customer_name}</span></div>` : ""}
					${(invoiceData.status === "Partly Paid" || (invoiceData.outstanding_amount && invoiceData.outstanding_amount > 0 && invoiceData.outstanding_amount < invoiceData.grand_total)) ? `<div class="partial-status"><span>${__("Status:")}</span><span>${__("PARTIAL PAYMENT")}</span></div>` : ""}
				</div>

				<div class="items-table">
					${invoiceData.items
						.map((item) => {
							const hasDiscount =
								(item.discount_percentage && Number.parseFloat(item.discount_percentage) > 0) ||
								(item.discount_amount && Number.parseFloat(item.discount_amount) > 0)
							const isFree = item.is_free_item
							const qty = item.quantity || item.qty
							const displayRate = item.price_list_rate || item.rate
							const subtotal = qty * displayRate
							return `
						<div class="item-row">
							<div class="item-name">${item.item_name || item.item_code} ${isFree ? __("(FREE)") : ""}</div>
							<div class="item-details">
								<span>${qty} × ${formatCurrency(displayRate)}</span>
								<span><strong>${formatCurrency(subtotal)}</strong></span>
							</div>
							${hasDiscount ? `<div class="item-discount"><span>Discount ${item.discount_percentage ? `(${Number(item.discount_percentage).toFixed(2)}%)` : ""}</span><span>-${formatCurrency(item.discount_amount || 0)}</span></div>` : ""}
							${item.serial_no ? `<div class="item-serials"><div class="item-serials-label">${__("Serial No:")}</div><div class="item-serials-list">${item.serial_no.replace(/\n/g, ", ")}</div></div>` : ""}
						</div>`
						})
						.join("")}
				</div>

				<div class="totals">
					${invoiceData.total_taxes_and_charges && invoiceData.total_taxes_and_charges > 0 ? `
					<div class="total-row"><span>${__("Subtotal:")}</span><span>${formatCurrency((invoiceData.grand_total || 0) - (invoiceData.total_taxes_and_charges || 0))}</span></div>
					<div class="total-row"><span>${__("Tax:")}</span><span>${formatCurrency(invoiceData.total_taxes_and_charges)}</span></div>` : ""}
					${invoiceData.discount_amount ? `
					<div class="total-row" style="color: #28a745;"><span>Additional Discount${invoiceData.additional_discount_percentage ? ` (${Number(invoiceData.additional_discount_percentage).toFixed(1)}%)` : ""}:</span><span>-${formatCurrency(Math.abs(invoiceData.discount_amount))}</span></div>` : ""}
					<div class="total-row grand-total"><span>${__("TOTAL:")}</span><span>${formatCurrency(invoiceData.grand_total)}</span></div>
				</div>

				${invoiceData.payments && invoiceData.payments.length > 0 ? `
				<div class="payments">
					<div style="font-weight: bold; margin-bottom: 5px; font-size: 12px;">${__("Payments:")}</div>
					${invoiceData.payments.map((p) => `<div class="payment-row"><span>${p.mode_of_payment}:</span><span>${formatCurrency(p.amount)}</span></div>`).join("")}
					<div class="payment-row total-paid"><span>${__("Total Paid:")}</span><span>${formatCurrency(invoiceData.paid_amount || 0)}</span></div>
					${invoiceData.change_amount && invoiceData.change_amount > 0 ? `<div class="payment-row" style="font-weight: bold; margin-top: 5px;"><span>${__("Change:")}</span><span>${formatCurrency(invoiceData.change_amount)}</span></div>` : ""}
					${invoiceData.outstanding_amount && invoiceData.outstanding_amount > 0 ? `<div class="outstanding-row"><span>${__("BALANCE DUE:")}</span><span>${formatCurrency(invoiceData.outstanding_amount)}</span></div>` : ""}
				</div>` : ""}

				<div class="footer">
					<div style="margin-bottom: 5px;">${invoiceData.footer || __("Thank you for your business!")}</div>
					${invoiceData.footer ? "" : `<div style="font-size: 10px;">Powered by <a href="https://nexus.brainwise.me" target="_blank" style="color: #3b82f6; text-decoration: none; font-weight: 600;">BrainWise</a></div>`}
				</div>
			</div>

			<div class="no-print" style="text-align: center; margin-top: 20px;">
				<button onclick="window.print()" style="padding: 10px 20px; font-size: 14px; cursor: pointer;">${__("Print Receipt")}</button>
				<button onclick="window.close()" style="padding: 10px 20px; font-size: 14px; cursor: pointer; margin-left: 10px;">${__("Close")}</button>
			</div>
		</body>
		</html>`

	printWindow.document.write(printContent)
	printWindow.document.close()
	printWindow.onload = () => {
		setTimeout(() => printWindow.print(), 250)
	}
}
