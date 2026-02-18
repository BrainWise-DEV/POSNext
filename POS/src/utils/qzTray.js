import qz from "qz-tray"
import { ref } from "vue"
import { call } from "@/utils/apiWrapper"
import { logger } from "@/utils/logger"

const log = logger.create("QZTray")

// ============================================================================
// Reactive State
// ============================================================================

/** Whether QZ Tray is currently connected */
export const qzConnected = ref(false)

/** Whether a connection attempt is in progress */
export const qzConnecting = ref(false)

/**
 * Certificate trust status:
 *   "unknown"   — not yet determined (no connection or no print attempted)
 *   "trusted"   — cert was provided AND first signing succeeded (silent print)
 *   "untrusted" — cert or signing failed (dialogs will appear)
 */
export const qzCertStatus = ref("unknown")

// ============================================================================
// localStorage Persistence
// ============================================================================

const PRINTER_STORAGE_KEY = "pos_qz_printer_name"

export function getSavedPrinterName() {
	try {
		return localStorage.getItem(PRINTER_STORAGE_KEY) || ""
	} catch {
		return ""
	}
}

export function savePrinterName(name) {
	try {
		localStorage.setItem(PRINTER_STORAGE_KEY, name || "")
	} catch (e) {
		log.warn("Failed to save printer name to localStorage:", e)
	}
}

// ============================================================================
// Security Setup (once)
// ============================================================================

let _securityInitialized = false

/** Cached certificate text — fetched once, reused for the session */
let _cachedCert = null

/** Whether the server has a valid cert to provide */
let _certProvided = false

function setupSecurity() {
	if (_securityInitialized) return
	_securityInitialized = true

	// Certificate callback — called once during WebSocket handshake.
	// Fetches the public cert from the server and caches it.
	qz.security.setCertificatePromise((resolve, reject) => {
		if (_cachedCert) {
			_certProvided = true
			resolve(_cachedCert)
			return
		}

		call("pos_next.api.qz.get_certificate")
			.then((cert) => {
				const pem = cert?.message || cert
				if (pem) {
					_cachedCert = pem
					_certProvided = true
				} else {
					_certProvided = false
					qzCertStatus.value = "untrusted"
				}
				resolve(pem)
			})
			.catch((err) => {
				log.warn("Could not fetch QZ certificate:", err?.message || err)
				_certProvided = false
				qzCertStatus.value = "untrusted"
				// Resolve empty so QZ falls back to unsigned (shows dialog)
				resolve()
			})
	})

	// Signature callback — called on every print/serial operation.
	// Sends the message to the server for RSA-SHA512 signing.
	qz.security.setSignatureAlgorithm("SHA512")
	qz.security.setSignaturePromise((toSign) => {
		return (resolve, reject) => {
			call("pos_next.api.qz.sign_message", { message: toSign })
				.then((sig) => {
					const signature = sig?.message || sig
					if (signature && _certProvided) {
						qzCertStatus.value = "trusted"
					}
					resolve(signature)
				})
				.catch((err) => {
					log.warn("Could not sign QZ message:", err?.message || err)
					qzCertStatus.value = "untrusted"
					// Resolve empty so QZ falls back to unsigned (shows dialog)
					resolve()
				})
		}
	})
}

// ============================================================================
// Connection Management
// ============================================================================

/** Guards against concurrent connect() calls */
let _connectPromise = null

/**
 * Connect to the locally-running QZ Tray application.
 * Singleton — concurrent calls share the same promise.
 * @returns {Promise<boolean>} true if connected successfully
 */
export async function connect() {
	if (qz.websocket.isActive()) {
		qzConnected.value = true
		return true
	}

	// Deduplicate concurrent calls
	if (_connectPromise) return _connectPromise

	_connectPromise = _doConnect()
	try {
		return await _connectPromise
	} finally {
		_connectPromise = null
	}
}

async function _doConnect() {
	setupSecurity()

	qz.websocket.setClosedCallbacks(() => {
		log.info("QZ Tray connection closed")
		qzConnected.value = false
		qzConnecting.value = false
		qzCertStatus.value = "unknown"
	})

	qzConnecting.value = true

	try {
		await qz.websocket.connect()
		qzConnected.value = true
		log.info("Connected to QZ Tray")

		// Probe trust status — findPrinters triggers the signature callback,
		// which updates qzCertStatus to "trusted" or "untrusted".
		qz.printers.find().catch(() => {})

		return true
	} catch (err) {
		qzConnected.value = false
		log.warn("Could not connect to QZ Tray:", err?.message || err)
		return false
	} finally {
		qzConnecting.value = false
	}
}

/**
 * Disconnect from QZ Tray.
 */
export async function disconnect() {
	if (!qz.websocket.isActive()) {
		qzConnected.value = false
		return
	}

	try {
		await qz.websocket.disconnect()
	} catch (err) {
		log.warn("Error disconnecting from QZ Tray:", err?.message || err)
	} finally {
		qzConnected.value = false
	}
}

// ============================================================================
// Printer Discovery
// ============================================================================

/**
 * List all printers available on the system via QZ Tray.
 * Connects automatically if not already connected.
 * @returns {Promise<string[]>} Array of printer names
 */
export async function findPrinters() {
	if (!qz.websocket.isActive()) {
		const ok = await connect()
		if (!ok) return []
	}

	try {
		const printers = await qz.printers.find()
		log.info(`Found ${printers.length} printer(s)`)
		return printers
	} catch (err) {
		log.error("Error discovering printers:", err?.message || err)
		return []
	}
}

// ============================================================================
// Print Dispatch
// ============================================================================

/**
 * Send rendered HTML to a printer via QZ Tray pixel printing.
 *
 * @param {string} html - Full HTML document string to print
 * @param {string} [printerName] - Target printer. Falls back to saved printer.
 * @param {Object} [options] - Extra print options
 * @param {number} [options.width] - Paper width in mm (default 80)
 * @param {string} [options.orientation] - "portrait" | "landscape" (default "portrait")
 * @returns {Promise<boolean>} true if print was dispatched successfully
 */
export async function printHTML(html, printerName, options = {}) {
	if (!qz.websocket.isActive()) {
		const ok = await connect()
		if (!ok) {
			throw new Error("QZ Tray is not available")
		}
	}

	const printer = printerName || getSavedPrinterName()
	if (!printer) {
		throw new Error("No printer selected. Please select a printer in POS Settings.")
	}

	const config = qz.configs.create(printer, {
		size: {
			width: options.width || 80,
			height: null, // auto height for receipts
		},
		units: "mm",
		orientation: options.orientation || "portrait",
		margins: { top: 0, right: 0, bottom: 0, left: 0 },
		colorType: "grayscale",
		interpolation: "nearest-neighbor",
	})

	const data = [
		{
			type: "pixel",
			format: "html",
			flavor: "plain",
			data: html,
		},
	]

	try {
		await qz.print(config, data)
		log.info(`Print job sent to "${printer}"`)
		return true
	} catch (err) {
		log.error(`Print failed on "${printer}":`, err?.message || err)
		throw err
	}
}
