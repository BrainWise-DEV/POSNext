/**
 * useDesktopUpdate — Tauri auto-updater integration.
 *
 * On boot (and every 6 hours) the composable asks Tauri whether a newer
 * version is available at the customer's `latest.json` endpoint. If so,
 * it exposes a reactive ref the UI can show a toast against; calling
 * `installAndRelaunch()` downloads + applies the update and restarts the app.
 *
 * No-op outside desktop mode.
 */

import { onMounted, ref } from "vue"
import { runtimeConfig } from "@/utils/runtimeConfig"
import { logger } from "@/utils/logger"

const log = logger.create("DesktopUpdate")
const CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000

const available = ref(null) // { version, notes } | null
const downloading = ref(false)
const error = ref(null)
let checkTimer = null
let updateHandle = null

async function loadUpdaterApi() {
	const mod = await import("@tauri-apps/plugin-updater")
	return mod
}

async function check() {
	if (!runtimeConfig.isDesktop) return null
	try {
		const { check: checkUpdate } = await loadUpdaterApi()
		const update = await checkUpdate()
		if (update?.available) {
			updateHandle = update
			available.value = {
				version: update.version,
				notes: update.body || "",
				date: update.date || null,
			}
			log.info("Desktop update available", available.value)
		} else {
			updateHandle = null
			available.value = null
		}
	} catch (err) {
		log.warn("Update check failed", err)
		error.value = err?.message || String(err)
	}
	return available.value
}

async function installAndRelaunch() {
	if (!runtimeConfig.isDesktop || !updateHandle) return
	downloading.value = true
	error.value = null
	try {
		await updateHandle.downloadAndInstall((event) => {
			log.debug("Update progress", event)
		})
		const { relaunch } = await import("@tauri-apps/plugin-process")
		await relaunch()
	} catch (err) {
		log.error("Update install failed", err)
		error.value = err?.message || String(err)
		downloading.value = false
	}
}

export function useDesktopUpdate({ autoCheck = true } = {}) {
	onMounted(() => {
		if (!runtimeConfig.isDesktop || !autoCheck) return
		check()
		if (!checkTimer) {
			checkTimer = setInterval(check, CHECK_INTERVAL_MS)
		}
	})

	return {
		available,
		downloading,
		error,
		check,
		installAndRelaunch,
	}
}
