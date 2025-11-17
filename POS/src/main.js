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
import { offlineWorker } from "./utils/offline/workerClient"
import translationPlugin from "./translation"

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

// Register service worker for PWA
if ("serviceWorker" in navigator) {
	window.addEventListener(
		"load",
		() => {
			import("virtual:pwa-register").then(({ registerSW }) => {
				registerSW({
					immediate: true,
					onNeedRefresh() {
						if (import.meta.env.DEV) {
							console.log("New content available, reloading...")
						}
					},
					onOfflineReady() {
						if (import.meta.env.DEV) {
							console.log("App ready to work offline")
						}
					},
					onRegistered(registration) {
						if (import.meta.env.DEV) {
							console.log("Service Worker registered:", registration)
						}
					},
					onRegisterError(error) {
						console.error("Service Worker registration error:", error)
					},
				})
			})
		},
		{ passive: true },
	)
}

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

// Helper to sync CSRF token to worker
async function syncCSRFTokenToWorker() {
	if (window.csrf_token && typeof window.csrf_token === 'string') {
		try {
			await offlineWorker.setCSRFToken(window.csrf_token)
			if (import.meta.env.DEV) {
				console.log("CSRF token synced to worker")
			}
		} catch (error) {
			if (import.meta.env.DEV) {
				console.warn("Failed to sync CSRF token to worker:", error)
			}
		}
	}
}

// Initialize CSRF token and user session before mounting
async function initializeApp() {
	// Set up the app - CSRF token will be initialized after login
	const app = createApp(App)
	const pinia = createPinia()

	// Register callback to sync CSRF token to worker whenever it's refreshed
	// This handles both periodic refreshes and automatic retry refreshes
	onCSRFTokenRefresh((newToken) => {
		offlineWorker.setCSRFToken(newToken).catch((error) => {
			if (import.meta.env.DEV) {
				console.warn("Failed to sync refreshed CSRF token to worker:", error)
			}
		})
	})

	// Wrap frappeRequest with CSRF auto-refresh
	const csrfAwareFrappeRequest = createCSRFAwareRequest(frappeRequest)
	setConfig("resourceFetcher", csrfAwareFrappeRequest)

	app.use(pinia)
	app.use(resourcesPlugin)
	app.use(pageMetaPlugin)
	app.use(translationPlugin)

	for (const key in globalComponents) {
		app.component(key, globalComponents[key])
	}

	// Add touch-action directive for mobile optimization
	app.directive("touch-action", {
		mounted(el) {
			el.style.touchAction = "manipulation"
		},
	})

	// Check authentication BEFORE registering router
	// This ensures session.user is set before router initializes

	// Initialize CSRF token if available
	const existingToken = getCSRFTokenFromCookie()
	if (existingToken) {
		if (import.meta.env.DEV) {
			console.log("CSRF token found in cookie, using it")
		}
		await syncCSRFTokenToWorker()
	} else {
		// No token in cookie, try to fetch one (this is a GET request, doesn't need CSRF)
		if (import.meta.env.DEV) {
			console.log("No CSRF token found, fetching...")
		}
		try {
			await ensureCSRFToken({ silent: true })
			await syncCSRFTokenToWorker()
		} catch (error) {
			if (import.meta.env.DEV) {
				console.log("CSRF token fetch failed, will retry on first API call")
			}
		}
	}

	// Fetch user BEFORE registering router - use .promise to ensure we wait properly
	try {
		// Trigger fetch if not already fetching
		if (!userResource.loading) {
			userResource.fetch()
		}
		// Wait for the fetch to complete
		await userResource.promise

		// Update session.user so that session.isLoggedIn is reactive and correct
		session.user = sessionUser()
		if (import.meta.env.DEV) {
			console.log(`[Main] User authenticated: ${session.user}`)
		}
	} catch (error) {
		// User not logged in - that's okay, they'll login and get the token then
		if (import.meta.env.DEV) {
			console.log("User not logged in:", error?.message || "No session")
		}
		// Make sure session.user is null
		session.user = null
	}

	// Initialize translations after CSRF token is ready
	if (window.$initTranslations) {
		try {
			await window.$initTranslations()
			if (import.meta.env.DEV) {
				console.log("Translations initialized")
			}
		} catch (error) {
			if (import.meta.env.DEV) {
				console.warn("Failed to initialize translations:", error)
			}
		}
	}

	// NOW register router after session.user is set
	if (import.meta.env.DEV) {
		console.log("[Main] Registering router with auth state:", session.isLoggedIn)
	}
	app.use(router)

	// Mount app AFTER authentication check and router registration
	app.mount("#app")

	// Set up periodic token refresh (every 30 minutes)
	setInterval(
		async () => {
			if (import.meta.env.DEV) {
				console.log("Performing scheduled CSRF token refresh...")
			}
			await ensureCSRFToken({ forceRefresh: true, silent: true })
			await syncCSRFTokenToWorker()
		},
		30 * 60 * 1000,
	) // 30 minutes
}

initializeApp()
