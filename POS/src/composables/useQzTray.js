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

export function useQzTray() {
	const { showSuccess, showError } = useToast()

	// ── State ──────────────────────────────────────────────────────────
	const printers = ref([])
	const selectedPrinter = ref(getSavedPrinterName())
	const loadingPrinters = ref(false)
	const certLoading = ref(false)
	const certReady = ref(false)

	const printerOptions = computed(() =>
		printers.value.map((p) => ({ label: p, value: p }))
	)

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
			const certPem = await call("pos_next.api.qz.get_certificate")
			const pem = certPem?.message || certPem
			if (!pem) {
				showError(__("Certificate not found. Generate it first."))
				return
			}
			const blob = new Blob([pem], { type: "application/x-pem-file" })
			const url = URL.createObjectURL(blob)
			const a = document.createElement("a")
			a.href = url
			a.download = "override.crt"
			document.body.appendChild(a)
			a.click()
			document.body.removeChild(a)
			URL.revokeObjectURL(url)
		} catch (error) {
			log.error("Failed to download QZ certificate:", error)
			showError(error?.message || __("Failed to download certificate."))
		}
	}

	async function checkCertificate() {
		try {
			const cert = await call("pos_next.api.qz.get_certificate")
			if (cert?.message || cert) {
				certReady.value = true
			}
		} catch {
			// Certificate doesn't exist yet — that's fine
		}
	}

	// ── Watchers ───────────────────────────────────────────────────────
	watch(selectedPrinter, (name) => {
		if (name) savePrinterName(name)
	})

	// ── Init ───────────────────────────────────────────────────────────
	checkCertificate()

	return {
		// Reactive state from qzTray.js
		qzConnected,
		qzConnecting,
		qzCertStatus,

		// Local state
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
