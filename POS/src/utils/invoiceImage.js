import { call } from "@/utils/apiWrapper"
import { logger } from "@/utils/logger"
import {
	buildReceiptDocumentHTML,
	hydrateLocalOnlyInvoice,
	isLocalOnlyInvoiceName,
	resolvePrintSettings,
} from "@/utils/printInvoice"
import { toCanvas } from "html-to-image"

const log = logger.create("InvoiceImage")

const FRAME_WIDTH_PX = 420
const FRAME_LOAD_TIMEOUT_MS = 20000

/**
 * Describe what to render for an invoice: the same /printview page the Print
 * button opens, or the built-in receipt for offline/local-only invoices.
 */
async function resolveInvoiceSource(invoiceData) {
	const invoice = await hydrateLocalOnlyInvoice(invoiceData)

	if (isLocalOnlyInvoiceName(invoice.name)) {
		if (!invoice.items?.length) {
			throw new Error(
				__(
					"This offline receipt is no longer in browser storage. Sync the invoice, then try again from history.",
				),
			)
		}
		return {
			srcdoc: buildReceiptDocumentHTML(invoice),
			selector: ".receipt",
		}
	}

	const doctype = invoice.doctype || "Sales Invoice"
	// Some invoice lists omit pos_profile; without it the
	// profile's print format would silently fall back to the default.
	let posProfile = invoice.pos_profile
	if (!posProfile) {
		try {
			posProfile = await call("frappe.client.get_value", {
				doctype,
				filters: { name: invoice.name },
				fieldname: "pos_profile",
			}).then((r) => (r?.message || r)?.pos_profile)
		} catch (err) {
			log.warn("Could not fetch invoice POS Profile:", err)
		}
	}

	const settings = await resolvePrintSettings(
		posProfile,
		invoice.print_format,
		null,
	)

	const params = new URLSearchParams({
		doctype,
		name: invoice.name,
		format: settings.printFormat,
		no_letterhead: settings.letterhead ? 0 : 1,
		_lang: "en",
		_t: Date.now(),
	})
	if (settings.letterhead) params.append("letterhead", settings.letterhead)

	return { src: `/printview?${params}`, selector: ".print-format" }
}

function loadFrame({ src, srcdoc }) {
	const frame = document.createElement("iframe")
	frame.setAttribute("aria-hidden", "true")
	frame.tabIndex = -1
	Object.assign(frame.style, {
		position: "fixed",
		left: "-10000px",
		top: "0",
		width: `${FRAME_WIDTH_PX}px`,
		height: "100px",
		border: "0",
		visibility: "hidden",
	})

	const loaded = new Promise((resolve, reject) => {
		const timer = setTimeout(
			() => reject(new Error(__("Timed out loading invoice"))),
			FRAME_LOAD_TIMEOUT_MS,
		)
		frame.onload = () => {
			clearTimeout(timer)
			resolve(frame)
		}
		frame.onerror = () => {
			clearTimeout(timer)
			reject(new Error(__("Failed to load invoice")))
		}
	})

	if (srcdoc !== undefined) frame.srcdoc = srcdoc
	else frame.src = src
	document.body.appendChild(frame)
	return { frame, loaded }
}

async function waitForAssets(doc) {
	const images = Array.from(doc.images).filter((img) => !img.complete)
	await Promise.all([
		doc.fonts?.ready,
		...images.map(
			(img) =>
				new Promise((resolve) => {
					img.onload = resolve
					img.onerror = resolve
				}),
		),
	])
}

/**
 * Render an invoice to an image blob ("image/png" or "image/jpeg").
 */
export async function renderInvoiceImage(invoiceData, type = "image/png") {
	const source = await resolveInvoiceSource(invoiceData)
	const { frame, loaded } = loadFrame(source)
	try {
		await loaded
		const doc = frame.contentDocument
		if (!doc?.body) throw new Error(__("Failed to load invoice"))
		await waitForAssets(doc)

		const target = doc.querySelector(source.selector) || doc.body
		// Frappe's screen styles give .print-format an A4 min-height, a drop
		// shadow and margins. The image size is measured from this node, so
		// strip them on the (throwaway) original rather than the clone.
		Object.assign(target.style, {
			minHeight: "0",
			boxShadow: "none",
			margin: "0",
		})
		// Size the frame to the content so nothing is clipped.
		frame.style.height = `${doc.documentElement.scrollHeight}px`

		const canvas = await toCanvas(target, {
			pixelRatio: 2,
			backgroundColor: "#ffffff",
		})
		// Encode here: html-to-image's toBlob ignores `type` and always emits PNG.
		const blob = await new Promise((resolve) =>
			canvas.toBlob(resolve, type, 0.92),
		)
		if (!blob) throw new Error(__("Failed to create invoice image"))
		return blob
	} finally {
		frame.remove()
	}
}

function downloadBlob(blob, filename) {
	const url = URL.createObjectURL(blob)
	const link = document.createElement("a")
	link.href = url
	link.download = filename
	document.body.appendChild(link)
	link.click()
	link.remove()
	setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/**
 * Copy the invoice image to the clipboard as PNG (the only image type browsers
 * accept there). Falls back to downloading a JPEG when the clipboard is
 * unavailable, e.g. over plain http or when permission is denied.
 * @returns {Promise<{method: "clipboard" | "download"}>}
 */
export async function copyInvoiceImage(invoiceData) {
	if (navigator.clipboard?.write && window.ClipboardItem) {
		// Pass the blob promise straight to ClipboardItem so Safari keeps the
		// user-gesture context across the async render.
		const pngPromise = renderInvoiceImage(invoiceData, "image/png")
		try {
			await navigator.clipboard.write([
				new ClipboardItem({ "image/png": pngPromise }),
			])
			return { method: "clipboard" }
		} catch (err) {
			// A render failure would fail the download too — surface it.
			await pngPromise
			log.warn("Clipboard write failed, downloading instead:", err)
		}
	}

	const jpeg = await renderInvoiceImage(invoiceData, "image/jpeg")
	downloadBlob(jpeg, `${invoiceData.name}.jpg`)
	return { method: "download" }
}
