import { computed, ref, watch } from "vue"
import { call } from "frappe-ui"
import { logger } from "@/utils/logger"
import { useToast } from "@/composables/useToast"
import {
	qzConnected,
	qzConnecting,
	qzCertStatus,
	connect as qzConnect,
	findPrinters,
	getSavedPrinterName,
	savePrinterName,
} from "@/utils/qzTray"

const log = logger.create("useQzTray")

const CERT_READY_KEY = "pos_qz_cert_ready"

// ── Singleton State (shared across all callers) ───────────────────────
const printers = ref([])
const selectedPrinter = ref(getSavedPrinterName())
const loadingPrinters = ref(false)
const certLoading = ref(false)
const certReady = ref(_loadCertReady())

const printerOptions = computed(() =>
	printers.value.map((p) => ({ label: p, value: p }))
)

function _buildCertFileName(company) {
	const safeName = company?.replace(/[^a-zA-Z0-9_\- ]/g, "").trim()
	return safeName ? `${safeName}.crt` : "certificate.crt"
}

// ── localStorage helpers ──────────────────────────────────────────────
function _loadCertReady() {
	try {
		return localStorage.getItem(CERT_READY_KEY) === "1"
	} catch {
		return false
	}
}

function _saveCertReady(value) {
	try {
		if (value) {
			localStorage.setItem(CERT_READY_KEY, "1")
		} else {
			localStorage.removeItem(CERT_READY_KEY)
		}
	} catch {
		// localStorage unavailable
	}
}

// ── Smart certificate check ───────────────────────────────────────────
// Only hits the server when we don't already know the cert exists.
// Once qzCertStatus becomes "trusted" (from actual QZ handshake),
// we persist that knowledge so future sessions skip the API call.
let _certChecked = false
function _checkCertificateOnce() {
	if (_certChecked) return
	_certChecked = true

	// Already confirmed from a previous session — skip API call
	if (certReady.value) return

	call("pos_next.api.qz.get_certificate")
		.then((cert) => {
			if (cert?.message || cert) {
				certReady.value = true
				_saveCertReady(true)
			}
		})
		.catch(() => {
			// Certificate doesn't exist yet — that's fine
		})
}
_checkCertificateOnce()

// Persist printer selection
watch(selectedPrinter, (name) => {
	if (name) savePrinterName(name)
})

// When QZ confirms trust, cache it for future sessions
watch(qzCertStatus, (status) => {
	if (status === "trusted") {
		certReady.value = true
		_saveCertReady(true)
	}
})

// ── Composable ────────────────────────────────────────────────────────
export function useQzTray() {
	const { showSuccess, showError } = useToast()

	// ── Connection ─────────────────────────────────────────────────────
	async function handleConnect() {
		const ok = await qzConnect()
		if (ok) {
			await refreshPrinters()
		}
	}

	// ── Printers ───────────────────────────────────────────────────────
	async function refreshPrinters() {
		loadingPrinters.value = true
		try {
			printers.value = await findPrinters()
			const saved = getSavedPrinterName()
			if (printers.value.length === 1) {
				selectedPrinter.value = printers.value[0]
				savePrinterName(selectedPrinter.value)
			} else if (saved && printers.value.includes(saved)) {
				selectedPrinter.value = saved
			}
		} finally {
			loadingPrinters.value = false
		}
	}

	// ── Certificate ────────────────────────────────────────────────────
	async function generateCertificate() {
		certLoading.value = true
		try {
			const result = await call("pos_next.api.qz.setup_qz_certificate")
			const data = result?.message || result
			certReady.value = true
			_saveCertReady(true)
			if (data?.status === "exists") {
				showSuccess(__("Certificate already exists. You can download it below."))
			} else {
				showSuccess(__("Certificate generated successfully."))
			}
		} catch (error) {
			log.error("Failed to setup QZ certificate:", error)
			showError(
				error?.messages?.[0] ||
				error?.message ||
				__("Failed to generate certificate. Are you a System Manager?")
			)
		} finally {
			certLoading.value = false
		}
	}

	async function downloadCertificate() {
		try {
			const result = await call("pos_next.api.qz.get_certificate_download")
			const data = result?.message || result
			if (!data?.pem) {
				showError(__("Certificate not found. Generate it first."))
				return
			}
			const blob = new Blob([data.pem], { type: "application/x-pem-file" })
			const url = URL.createObjectURL(blob)
			const a = document.createElement("a")
			a.href = url
			a.download = _buildCertFileName(data.company)
			document.body.appendChild(a)
			a.click()
			document.body.removeChild(a)
			URL.revokeObjectURL(url)
		} catch (error) {
			log.error("Failed to download QZ certificate:", error)
			showError(error?.message || __("Failed to download certificate."))
		}
	}

	return {
		// Reactive state from qzTray.js
		qzConnected,
		qzConnecting,
		qzCertStatus,

		// Shared singleton state
		printers,
		selectedPrinter,
		loadingPrinters,
		printerOptions,
		certLoading,
		certReady,

		// Actions
		handleConnect,
		refreshPrinters,
		generateCertificate,
		downloadCertificate,
	}
}
