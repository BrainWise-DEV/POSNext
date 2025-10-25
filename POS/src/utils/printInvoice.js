import { call } from "@/utils/apiWrapper"

/**
 * Print invoice using Frappe's print format system
 * @param {Object} invoiceData - The invoice document data
 * @param {string} printFormat - The print format name (optional)
 * @param {string} letterhead - The letterhead name (optional)
 */
export async function printInvoice(
	invoiceData,
	printFormat = null,
	letterhead = null,
) {
	try {
		if (!invoiceData || !invoiceData.name) {
			throw new Error("Invalid invoice data")
		}

		const doctype = invoiceData.doctype || "Sales Invoice"
		const format = printFormat || "POS Next Receipt"

		// Build PDF print URL
		const params = new URLSearchParams({
			doctype: doctype,
			name: invoiceData.name,
			format: format,
			no_letterhead: letterhead ? 0 : 1,
			_lang: "en",
			trigger_print: 1,
		})

		if (letterhead) {
			params.append("letterhead", letterhead)
		}

		// Open PDF in new window - browser will handle print dialog
		const printUrl = `/api/method/frappe.utils.print_format.download_pdf?${params.toString()}`
		const printWindow = window.open(printUrl, "_blank", "width=800,height=600")

		if (!printWindow) {
			throw new Error(
				"Failed to open print window. Please check your popup blocker settings.",
			)
		}

		return true
	} catch (error) {
		console.error("Error printing with Frappe print format:", error)
		// Fallback to custom print format
		return printInvoiceCustom(invoiceData)
	}
}

/**
 * Custom print format as fallback
 * @param {Object} invoiceData - The invoice document data
 */
function printInvoiceCustom(invoiceData) {
	const printWindow = window.open("", "_blank", "width=800,height=600")

	const printContent = `
		<!DOCTYPE html>
		<html>
		<head>
			<meta charset="UTF-8">
			<title>Invoice - ${invoiceData.name}</title>
			<style>
				* {
					margin: 0;
					padding: 0;
					box-sizing: border-box;
				}

				body {
					font-family: 'Courier New', monospace;
					padding: 20px;
					width: 80mm;
					margin: 0 auto;
				}

				.receipt {
					width: 100%;
				}

				.header {
					text-align: center;
					margin-bottom: 20px;
					border-bottom: 2px dashed #000;
					padding-bottom: 10px;
				}

				.company-name {
					font-size: 18px;
					font-weight: bold;
					margin-bottom: 5px;
				}

				.invoice-info {
					margin-bottom: 15px;
					font-size: 12px;
				}

				.invoice-info div {
					display: flex;
					justify-content: space-between;
					margin-bottom: 3px;
				}

				.partial-status {
					color: #dc3545;
					font-weight: bold;
					margin-bottom: 5px;
				}

				.items-table {
					width: 100%;
					margin-bottom: 15px;
					border-top: 1px dashed #000;
					border-bottom: 1px dashed #000;
					padding: 10px 0;
				}

				.item-row {
					margin-bottom: 10px;
					font-size: 12px;
				}

				.item-name {
					font-weight: bold;
					margin-bottom: 3px;
				}

				.item-details {
					display: flex;
					justify-content: space-between;
					font-size: 11px;
					color: #333;
				}

				.item-discount {
					display: flex;
					justify-content: space-between;
					font-size: 10px;
					color: #28a745;
					margin-top: 2px;
				}

				.totals {
					margin-top: 15px;
					border-top: 1px dashed #000;
					padding-top: 10px;
				}

				.total-row {
					display: flex;
					justify-content: space-between;
					margin-bottom: 5px;
					font-size: 12px;
				}

				.grand-total {
					font-size: 16px;
					font-weight: bold;
					border-top: 2px solid #000;
					padding-top: 10px;
					margin-top: 10px;
				}

				.payments {
					margin-top: 15px;
					border-top: 1px dashed #000;
					padding-top: 10px;
				}

				.payment-row {
					display: flex;
					justify-content: space-between;
					margin-bottom: 3px;
					font-size: 11px;
				}

				.total-paid {
					font-weight: bold;
					border-top: 1px solid #ccc;
					padding-top: 5px;
					margin-top: 5px;
				}

				.outstanding-row {
					display: flex;
					justify-content: space-between;
					font-size: 13px;
					font-weight: bold;
					color: #dc3545;
					background-color: #fff3cd;
					padding: 8px;
					margin-top: 8px;
					border-radius: 4px;
				}

				.footer {
					text-align: center;
					margin-top: 20px;
					padding-top: 10px;
					border-top: 2px dashed #000;
					font-size: 11px;
				}

				@media print {
					body {
						padding: 0;
					}

					.no-print {
						display: none;
					}
				}
			</style>
		</head>
		<body>
			<div class="receipt">
				<!-- Header -->
				<div class="header">
					<div class="company-name">${invoiceData.company || "POS Next"}</div>
					<div style="font-size: 12px;">TAX INVOICE</div>
				</div>

				<!-- Invoice Info -->
				<div class="invoice-info">
					<div>
						<span>Invoice #:</span>
						<span><strong>${invoiceData.name}</strong></span>
					</div>
					<div>
						<span>Date:</span>
						<span>${new Date(invoiceData.posting_date || Date.now()).toLocaleString()}</span>
					</div>
					${
						invoiceData.customer_name
							? `
					<div>
						<span>Customer:</span>
						<span>${invoiceData.customer_name}</span>
					</div>
					`
							: ""
					}
					${
						(invoiceData.status === "Partly Paid" || (invoiceData.outstanding_amount && invoiceData.outstanding_amount > 0 && invoiceData.outstanding_amount < invoiceData.grand_total))
							? `
					<div class="partial-status">
						<span>Status:</span>
						<span>PARTIAL PAYMENT</span>
					</div>
					`
							: ""
					}
				</div>

				<!-- Items -->
				<div class="items-table">
					${invoiceData.items
						.map((item) => {
							const hasItemDiscount =
								(item.discount_percentage &&
									Number.parseFloat(item.discount_percentage) > 0) ||
								(item.discount_amount &&
									Number.parseFloat(item.discount_amount) > 0)
							const isFree = item.is_free_item
							const qty = item.qty || item.quantity
							const amount = item.amount || item.rate * qty

							return `
						<div class="item-row">
							<div class="item-name">
								${item.item_name || item.item_code}${isFree ? " (FREE)" : ""}
							</div>
							<div class="item-details">
								<span>${qty} × ${formatCurrency(item.rate)}</span>
								<span><strong>${formatCurrency(amount)}</strong></span>
							</div>
							${
								hasItemDiscount
									? `
							<div class="item-discount">
								<span>Discount ${item.discount_percentage ? `(${item.discount_percentage}%)` : ""}</span>
								<span>-${formatCurrency(item.discount_amount || 0)}</span>
							</div>
							`
									: ""
							}
						</div>
						`
						})
						.join("")}
				</div>

				<!-- Totals -->
				<div class="totals">
					${
						invoiceData.total_taxes_and_charges &&
						invoiceData.total_taxes_and_charges > 0
							? `
					<div class="total-row">
						<span>Subtotal:</span>
						<span>${formatCurrency((invoiceData.grand_total || 0) - (invoiceData.total_taxes_and_charges || 0))}</span>
					</div>
					<div class="total-row">
						<span>Tax:</span>
						<span>${formatCurrency(invoiceData.total_taxes_and_charges)}</span>
					</div>
					`
							: ""
					}
					<div class="total-row grand-total">
						<span>TOTAL:</span>
						<span>${formatCurrency(invoiceData.grand_total)}</span>
					</div>
				</div>

				<!-- Payments -->
				${
					invoiceData.payments && invoiceData.payments.length > 0
						? `
				<div class="payments">
					<div style="font-weight: bold; margin-bottom: 5px; font-size: 12px;">Payments:</div>
					${invoiceData.payments
						.map(
							(payment) => `
						<div class="payment-row">
							<span>${payment.mode_of_payment}:</span>
							<span>${formatCurrency(payment.amount)}</span>
						</div>
					`,
						)
						.join("")}
					<div class="payment-row total-paid">
						<span>Total Paid:</span>
						<span>${formatCurrency(invoiceData.paid_amount || 0)}</span>
					</div>
					${
						invoiceData.change_amount && invoiceData.change_amount > 0
							? `
					<div class="payment-row" style="font-weight: bold; margin-top: 5px;">
						<span>Change:</span>
						<span>${formatCurrency(invoiceData.change_amount)}</span>
					</div>
					`
							: ""
					}
					${
						invoiceData.outstanding_amount && invoiceData.outstanding_amount > 0
							? `
					<div class="outstanding-row">
						<span>BALANCE DUE:</span>
						<span>${formatCurrency(invoiceData.outstanding_amount)}</span>
					</div>
					`
							: ""
					}
				</div>
				`
						: ""
				}

				<!-- Footer -->
				<div class="footer">
					<div style="margin-bottom: 5px;">Thank you for your business!</div>
					<div style="font-size: 10px;">Powered by POS Next</div>
				</div>
			</div>

			<div class="no-print" style="text-align: center; margin-top: 20px;">
				<button onclick="window.print()" style="padding: 10px 20px; font-size: 14px; cursor: pointer;">
					Print Receipt
				</button>
				<button onclick="window.close()" style="padding: 10px 20px; font-size: 14px; cursor: pointer; margin-left: 10px;">
					Close
				</button>
			</div>
		</body>
		</html>
	`

	printWindow.document.write(printContent)
	printWindow.document.close()

	// Auto print after load
	printWindow.onload = () => {
		setTimeout(() => {
			printWindow.print()
		}, 250)
	}
}

function formatCurrency(amount) {
	return Number.parseFloat(amount || 0).toFixed(2)
}

/**
 * Print invoice by name, fetching print format from POS Profile
 * @param {string} invoiceName - The name of the invoice to print
 * @param {string} printFormat - Optional print format override
 * @param {string} letterhead - Optional letterhead override
 */
export async function printInvoiceByName(
	invoiceName,
	printFormat = null,
	letterhead = null,
) {
	try {
		// Fetch the invoice document
		const invoiceDoc = await call("frappe.client.get", {
			doctype: "Sales Invoice",
			name: invoiceName,
		})

		if (!invoiceDoc) {
			throw new Error("Invoice not found")
		}

		// If no print format specified and invoice has a POS Profile, fetch its print settings
		if (!printFormat && invoiceDoc.pos_profile) {
			try {
				const posProfileDoc = await call("frappe.client.get", {
					doctype: "POS Profile",
					name: invoiceDoc.pos_profile,
				})

				if (posProfileDoc) {
					printFormat = posProfileDoc.print_format
					letterhead = letterhead || posProfileDoc.letter_head
				}
			} catch (error) {
				console.warn("Could not fetch POS Profile print settings:", error)
				// Continue with default print format
			}
		}

		// Print the invoice
		return await printInvoice(invoiceDoc, printFormat, letterhead)
	} catch (error) {
		console.error("Error fetching invoice for print:", error)
		throw error
	}
}
