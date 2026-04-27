/**
 * POS Next - Application Entry Point
 *
 * Initialization sequence:
 * 1. Register PWA service worker
 * 2. Configure Vue app with plugins and global components
 * 3. Authenticate user and initialize CSRF token (in parallel)
 * 4. Preload bootstrap data for faster page rendering
 * 5. Register router and mount app
 */

import { createPinia } from "pinia"
import { createApp } from "vue"

import App from "./App.vue"
import { session, sessionUser } from "./data/session"
import { userResource } from "./data/user"
import router from "./router"
import {
	createCSRFAwareRequest,
	ensureCSRFToken,
	getCSRFTokenFromCookie,
	onCSRFTokenRefresh,
} from "./utils/csrf"
import { logger } from "./utils/logger"
import { offlineWorker } from "./utils/offline/workerClient"
import translationPlugin from "./utils/translation"
import { initSocket } from "./socket"
import { runtimeConfig, getAuthHeader } from "./utils/runtimeConfig"
import { desktopFrappeRequest } from "./utils/desktopTransport"
import { restoreApiCredentialsFromStronghold } from "./utils/desktopAuth"

import {
	Alert,
	Badge,
	Button,
	Dialog,
	ErrorMessage,
	FormControl,
	Input,
	TextInput,
	frappeRequest,
	pageMetaPlugin,
	resourcesPlugin,
	setConfig,
} from "frappe-ui"

import "./index.css"

const log = logger.create("Main")

// =============================================================================
// PWA Service Worker Registration
// =============================================================================

if (runtimeConfig.hasServiceWorker && "serviceWorker" in navigator) {
	window.addEventListener(
		"load",
		() => {
			import("virtual:pwa-register").then(({ registerSW }) => {
				registerSW({
					immediate: true,
					onNeedRefresh: () => log.info("New content available, reloading..."),
					onOfflineReady: () => log.info("App ready to work offline"),
					onRegistered: (reg) => log.info("Service Worker registered", reg),
					onRegisterError: (err) =>
						log.error("Service Worker registration error", err),
				})
			})
		},
		{ passive: true },
	)
}

// =============================================================================
// Global Components (available in all templates without import)
// =============================================================================

const globalComponents = {
	Button,
	TextInput,
	Input,
	FormControl,
	ErrorMessage,
	Dialog,
	Alert,
	Badge,
}

// =============================================================================
// CSRF Token Management
// =============================================================================

/** Sync CSRF token to offline worker for authenticated API calls */
async function syncCSRFTokenToWorker() {
	if (window.csrf_token && typeof window.csrf_token === "string") {
		try {
			await offlineWorker.setCSRFToken(window.csrf_token)
			log.debug("CSRF token synced to worker")
		} catch (error) {
			log.warn("Failed to sync CSRF token to worker", error)
		}
	}
}

/** Push the desktop API config (baseUrl + Authorization header) into the worker. */
async function syncApiConfigToWorker() {
	try {
		await offlineWorker.setApiConfig({
			baseUrl: runtimeConfig.baseUrl,
			authHeader: getAuthHeader(),
		})
		log.debug("API config synced to worker")
	} catch (error) {
		log.warn("Failed to sync API config to worker", error)
	}
}

// =============================================================================
// Application Initialization
// =============================================================================

async function initializeApp() {
	const app = createApp(App)
	const pinia = createPinia()

	if (runtimeConfig.isDesktop) {
		// Route every frappe-ui resource through the Tauri Rust HTTP plugin.
		// CSRF + cookies don't apply; auth is via API key/secret in Stronghold.
		setConfig("resourceFetcher", desktopFrappeRequest)
	} else {
		// Keep worker in sync when CSRF token refreshes
		onCSRFTokenRefresh((newToken) => {
			offlineWorker.setCSRFToken(newToken).catch((error) => {
				log.warn("Failed to sync refreshed CSRF token to worker", error)
			})
		})

		// Enable automatic CSRF token refresh on 401/403 errors
		const csrfAwareFrappeRequest = createCSRFAwareRequest(frappeRequest)
		setConfig("resourceFetcher", csrfAwareFrappeRequest)
	}

	// Register plugins
	app.use(pinia)
	app.use(resourcesPlugin)
	app.use(pageMetaPlugin)
	app.use(translationPlugin)

	// Register global components
	for (const key in globalComponents) {
		app.component(key, globalComponents[key])
	}

	// Disable double-tap zoom on mobile for faster touch response
	app.directive("touch-action", {
		mounted: (el) => (el.style.touchAction = "manipulation"),
	})

	// -------------------------------------------------------------------------
	// Authentication
	//   - Web: CSRF + user resource fetched in parallel.
	//   - Desktop: load API key/secret from Stronghold, then resolve the user
	//     via the same userResource (which now goes through the desktop transport).
	// -------------------------------------------------------------------------

	let user = null

	if (runtimeConfig.isDesktop) {
		try {
			const restored = await restoreApiCredentialsFromStronghold()
			if (restored) {
				log.info("Restored API credentials from Stronghold")
				await syncApiConfigToWorker()
			} else {
				log.info("No stored credentials — login required")
			}
		} catch (error) {
			log.warn("Stronghold restore failed", error)
		}

		if (getAuthHeader()) {
			try {
				if (!userResource.loading) userResource.fetch()
				await userResource.promise
				user = sessionUser()
			} catch (error) {
				log.debug(
					"Desktop user fetch failed (likely invalid creds)",
					error?.message || error,
				)
				user = null
			}
		}
	} else {
		const csrfPromise = (async () => {
			const existingToken = getCSRFTokenFromCookie()
			if (existingToken) {
				log.debug("CSRF token found in cookie")
				await syncCSRFTokenToWorker()
				return true
			}

			log.debug("Fetching CSRF token...")
			try {
				await ensureCSRFToken({ silent: true })
				await syncCSRFTokenToWorker()
				return true
			} catch {
				log.debug("CSRF fetch failed, will retry on first API call")
				return false
			}
		})()

		const userPromise = (async () => {
			try {
				if (!userResource.loading) userResource.fetch()
				await userResource.promise
				return sessionUser()
			} catch (error) {
				log.debug("User not logged in", error?.message || "No session")
				return null
			}
		})()

		const [, fetchedUser] = await Promise.all([csrfPromise, userPromise])
		user = fetchedUser
	}

	session.user = user
	log.info(`User authenticated: ${session.user}`)

	// -------------------------------------------------------------------------
	// Bootstrap Preload (non-blocking, improves perceived performance)
	// -------------------------------------------------------------------------

	if (user) {
		// Make sure the worker can reach the backend before we kick off any
		// preload (CACHE_ITEMS etc. are no-ops without auth in desktop mode).
		if (runtimeConfig.isDesktop) {
			await syncApiConfigToWorker()
		}

		import("./stores/bootstrap")
			.then(async ({ useBootstrapStore }) => {
				const bootstrapStore = useBootstrapStore()
				try {
					await bootstrapStore.loadInitialData()
					// Initialize precision settings from bootstrap data
					const { initPrecision } = await import("./utils/currency")
					initPrecision(bootstrapStore.getPreloadedPrecision())
					log.debug("Precision settings initialized from bootstrap")

					// Initialize Socket.IO with correct site name from bootstrap.
					// Desktop builds skip realtime entirely (no cookie auth across origins).
					if (runtimeConfig.hasRealtime && typeof window !== "undefined") {
						if (!window.frappe) window.frappe = {}
						const siteName = bootstrapStore.getSiteName()
						window.frappe.realtime = initSocket(siteName)

						// Ensure connection is established
						if (
							window.frappe.realtime &&
							typeof window.frappe.realtime.connect === "function"
						) {
							window.frappe.realtime.connect()
							log.info("Socket initialized and connecting...", { siteName })
						}
					}
				} catch (error) {
					log.debug("Bootstrap preload failed (non-critical)", error)
				}
			})
			.catch(() => {})

		// Durability layers — both fire-and-forget. Independent of bootstrap.
		// 1. Ask the browser to keep our IndexedDB even under storage pressure.
		import("./utils/offline/persistence")
			.then(({ ensurePersistentStorage }) =>
				ensurePersistentStorage()
					.then((status) =>
						log.info("Persistent storage status", {
							supported: status.supported,
							persisted: status.persisted,
						}),
					)
					.catch(() => {}),
			)
			.catch(() => {})

		// 2. Restore any QZ-Tray on-disk mirror that survived a browser
		//    wipe back into IndexedDB. Best-effort — no-op if QZ isn't
		//    running. Runs after a short delay so QZ has a chance to
		//    auto-connect from the print path.
		setTimeout(() => {
			import("./utils/offline/diskBackup")
				.then(({ restoreFromDisk }) => restoreFromDisk())
				.then((res) => {
					if (res?.ran && (res.invoicesRestored || res.customersRestored)) {
						log.warn(
							`Restored from disk mirror: ${res.invoicesRestored} invoices + ${res.customersRestored} customers`,
						)
					}
				})
				.catch(() => {})
		}, 5000)
	}

	// -------------------------------------------------------------------------
	// Mount Application
	// -------------------------------------------------------------------------

	log.debug("Registering router, auth state:", session.isLoggedIn)
	app.use(router)
	app.mount("#app")

	// -------------------------------------------------------------------------
	// Scheduled CSRF Token Refresh (web only — desktop has no CSRF)
	// -------------------------------------------------------------------------

	if (!runtimeConfig.isDesktop) {
		setInterval(
			async () => {
				log.debug("Scheduled CSRF token refresh")
				await ensureCSRFToken({ forceRefresh: true, silent: true })
				await syncCSRFTokenToWorker()
			},
			30 * 60 * 1000,
		)
	}
}

initializeApp()
