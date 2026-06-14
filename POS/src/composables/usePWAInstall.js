import { onMounted, onUnmounted, ref } from "vue"

const DISMISS_KEY = "pwa-install-dismissed"
const DISMISS_WINDOW_DAYS = 7
const DISMISS_WINDOW_MS = DISMISS_WINDOW_DAYS * 24 * 60 * 60 * 1000

const isClient = () => typeof window !== "undefined"

const isStandaloneDisplay = () => {
	if (!isClient()) return false
	return (
		window.matchMedia("(display-mode: standalone)").matches ||
		window.navigator.standalone === true
	)
}

const hasActiveDismissal = () => {
	if (!isClient()) return false
	try {
		const stored = localStorage.getItem(DISMISS_KEY)
		if (!stored) return false
		const dismissedAt = new Date(stored).getTime()
		if (Number.isNaN(dismissedAt)) {
			localStorage.removeItem(DISMISS_KEY)
			return false
		}

		if (Date.now() - dismissedAt < DISMISS_WINDOW_MS) {
			return true
		}

		localStorage.removeItem(DISMISS_KEY)
		return false
	} catch (error) {
		console.warn("[PWA] Failed to read dismissal state", error)
		return false
	}
}

export function usePWAInstall() {
	const deferredPrompt = ref(null)
	const isInstallable = ref(false)
	const isInstalled = ref(false)
	const showInstallBadge = ref(false)

	const updateInstalledState = () => {
		const installed = isStandaloneDisplay()
		isInstalled.value = installed
		if (installed) {
			isInstallable.value = false
			showInstallBadge.value = false
			if (isClient()) {
				try {
					localStorage.removeItem(DISMISS_KEY)
				} catch (error) {
					console.warn("[PWA] Failed to clear dismissal state", error)
				}
			}
		}
		return installed
	}

	const handleBeforeInstallPrompt = (event) => {
		event.preventDefault()
		deferredPrompt.value = event
		isInstallable.value = true
		if (!isInstalled.value && !hasActiveDismissal()) {
			showInstallBadge.value = true
		}
	}

	const handleAppInstalled = () => {
		deferredPrompt.value = null
		updateInstalledState()
	}

	const handleVisibilityChange = () => {
		if (document.visibilityState === "visible") {
			updateInstalledState()
		}
	}

	onMounted(() => {
		if (updateInstalledState()) {
			return
		}

		window.addEventListener("beforeinstallprompt", handleBeforeInstallPrompt)
		window.addEventListener("appinstalled", handleAppInstalled)
		if (typeof document !== "undefined") {
			document.addEventListener("visibilitychange", handleVisibilityChange)
		}
	})

	onUnmounted(() => {
		window.removeEventListener("beforeinstallprompt", handleBeforeInstallPrompt)
		window.removeEventListener("appinstalled", handleAppInstalled)
		if (typeof document !== "undefined") {
			document.removeEventListener("visibilitychange", handleVisibilityChange)
		}
	})

	const promptInstall = async () => {
		if (!deferredPrompt.value) {
			return false
		}

		deferredPrompt.value.prompt()
		const { outcome } = await deferredPrompt.value.userChoice
		deferredPrompt.value = null
		isInstallable.value = false
		if (outcome === "accepted") {
			showInstallBadge.value = false
			updateInstalledState()
			return true
		}

		showInstallBadge.value = false
		return false
	}

	const dismissBadge = () => {
		showInstallBadge.value = false
	}

	const snoozeBadge = () => {
		showInstallBadge.value = false
		if (!isClient()) return
		try {
			localStorage.setItem(DISMISS_KEY, new Date().toISOString())
		} catch (error) {
			console.warn("[PWA] Failed to snooze install badge", error)
		}
	}

	return {
		isInstallable,
		isInstalled,
		showInstallBadge,
		promptInstall,
		dismissBadge,
		snoozeBadge,
	}
}
