import { ref, computed, onMounted } from "vue"
import { translationVersion } from "../utils/translation"
import { call } from "../utils/apiWrapper"
import { offlineState } from "../utils/offline/offlineState"
import { logger } from "../utils/logger"
import { useBootstrapStore } from "../stores/bootstrap"

const log = logger.create("Locale")

// Reactive locale state (shared across all components)
const currentLocale = ref("en")
const currentDir = ref("ltr")
const allowedLocales = ref(null) // null = not fetched yet, array = fetched from server
const PREFARED_LANGUAGE_KEY = "pos_next_language"
const ALLOWED_LOCALES_KEY = "pos_next_allowed_locales"

/** Track if initial language fetch from server has been attempted */
let serverLanguageFetched = false

// Get flag URL from flagcdn.com
function getFlagUrl(countryCode) {
	if (!countryCode) return null
	return `https://flagcdn.com/h24/${countryCode.toLowerCase()}.png`
}

// Get flag SVG URL from flagcdn.com
function getFlagUrlSvg(countryCode) {
	if (!countryCode) return null
	return `https://flagcdn.com/${countryCode.toLowerCase()}.svg`
}

// Supported languages configuration
export const SUPPORTED_LOCALES = {
	en: {
		name: "English",
		nativeName: "English",
		countryCode: "us",
		dir: "ltr",
	},
	ar: {
		name: "Arabic",
		nativeName: "العربية",
		countryCode: "eg",
		dir: "rtl",
	},
	id: {
		name: "Indonesian",
		nativeName: "Bahasa",
		countryCode: "id",
		dir: "ltr",
	},
	"pt-br": {
		name: "Portuguese (Brazil)",
		nativeName: "Portugues (Brasil)",
		countryCode: "br",
		dir: "ltr",
	}
}

/**
 * Fetch allowed locales from POS Settings
 * Caches result in localStorage for offline use
 * @returns {Promise<string[]|null>} Array of allowed locale codes or null if fetch fails
 */
async function fetchAllowedLocalesFromServer() {
	try {
		const response = await call("pos_next.api.localization.get_allowed_locales", {})
		if (response?.locales && Array.isArray(response.locales)) {
			// Cache for offline use
			localStorage.setItem(ALLOWED_LOCALES_KEY, JSON.stringify(response.locales))
			return response.locales
		}
	} catch (error) {
		log.warn("Failed to fetch allowed locales from server", error)
	}
	return null
}

/**
 * Get cached allowed locales from localStorage
 * @returns {string[]|null} Array of allowed locale codes or null
 */
function getCachedAllowedLocales() {
	try {
		const cached = localStorage.getItem(ALLOWED_LOCALES_KEY)
		if (cached) {
			return JSON.parse(cached)
		}
	} catch (error) {
		log.warn("Failed to parse cached allowed locales", error)
	}
	return null
}

/**
 * Fetch user's language preference from the server
 * Checks bootstrap store first for preloaded data to avoid redundant API call
 * @returns {Promise<string|null>} Language code or null if fetch fails
 */
async function fetchLanguageFromServer() {
	// OPTIMIZATION: Check if bootstrap has preloaded the locale
	try {
		const bootstrapStore = useBootstrapStore()
		const preloadedLocale = bootstrapStore.getPreloadedLocale()
		if (preloadedLocale && SUPPORTED_LOCALES[preloadedLocale]) {
			log.info(`Using preloaded language from bootstrap: ${preloadedLocale}`)
			return preloadedLocale
		}
	} catch (error) {
		// Bootstrap store may not be available yet, fall through to API call
		log.debug("Bootstrap store not available, fetching language from API")
	}

	// Fallback to direct API call
	try {
		const response = await call("pos_next.api.localization.get_user_language", {})
		if (response?.locale && SUPPORTED_LOCALES[response.locale]) {
			log.info(`Fetched language from server: ${response.locale}`)
			return response.locale
		}
	} catch (error) {
		log.warn("Failed to fetch language from server", error)
	}
	return null
}

/**
 * Detect current language from cache sources (when offline)
 * Priority: Frappe boot → localStorage → browser → default
 * @returns {string} Language code
 */
function detectCachedLanguage() {
	// 1. Check Frappe boot data (user's saved preference)
	if (typeof window !== "undefined" && window.frappe?.boot?.lang) {
		const lang = window.frappe.boot.lang.toLowerCase()
		if (SUPPORTED_LOCALES[lang]) {
			return lang
		}
	}

	// 2. Check localStorage
	const stored = localStorage.getItem(PREFARED_LANGUAGE_KEY)
	if (stored && SUPPORTED_LOCALES[stored]) {
		return stored
	}

	// 3. Check browser language
	const browserLang = navigator.language.split("-")[0].toLowerCase()
	if (SUPPORTED_LOCALES[browserLang]) {
		return browserLang
	}

	// 4. Default to English
	return "en"
}

/**
 * Composable for locale management
 * Provides reactive locale state and methods to change language
 */
export function useLocale() {
	// Computed properties
	const locale = computed(() => currentLocale.value)
	const dir = computed(() => currentDir.value)
	const isRTL = computed(() => currentDir.value === "rtl")
	const localeConfig = computed(() => {
		const config = SUPPORTED_LOCALES[locale.value] || SUPPORTED_LOCALES.en
		return {
			...config,
			flagUrl: getFlagUrl(config.countryCode),
			flagUrlSvg: getFlagUrlSvg(config.countryCode),
		}
	})

	/**
	 * Change application language
	 * Updates document direction, saves preference, and uses translation system
	 * @param {string} newLocale - Language code (e.g., 'ar', 'en', 'fr')
	 */
	async function changeLocale(newLocale) {
		if (!SUPPORTED_LOCALES[newLocale]) {
			console.warn(`Locale ${newLocale} not supported`)
			return
		}

		const config = SUPPORTED_LOCALES[newLocale]

		// Update reactive refs
		currentLocale.value = newLocale
		currentDir.value = config.dir

		// Update document attributes
		document.documentElement.setAttribute("dir", config.dir)
		document.documentElement.setAttribute("lang", newLocale)

		// Toggle RTL class for CSS
		if (config.dir === "rtl") {
			document.documentElement.classList.add("rtl")
		} else {
			document.documentElement.classList.remove("rtl")
		}

		// Store preference in localStorage
		localStorage.setItem(PREFARED_LANGUAGE_KEY, newLocale)

		// Update Frappe user settings first (this changes the user's language in Frappe)
		try {
			await call("pos_next.api.localization.change_user_language", {
				locale: newLocale,
			})
		} catch (error) {
			console.error("Failed to save language preference to Frappe:", error)
		}

		// Fetch new translations dynamically (no page reload needed)
		// The API returns translations based on the user's current Frappe language setting
		if (typeof window !== "undefined" && window.$changeLanguage) {
			try {
				await window.$changeLanguage(newLocale)
			} catch (error) {
				console.error("Failed to load translations:", error)
			}
		}
	}

	/**
	 * Apply locale to document and reactive state
	 * @param {string} locale - Language code to apply
	 */
	function applyLocale(locale) {
		const config = SUPPORTED_LOCALES[locale]
		if (!config) return

		currentLocale.value = locale
		currentDir.value = config.dir

		// Set document attributes
		if (typeof document !== "undefined") {
			document.documentElement.setAttribute("dir", config.dir)
			document.documentElement.setAttribute("lang", locale)

			if (config.dir === "rtl") {
				document.documentElement.classList.add("rtl")
			} else {
				document.documentElement.classList.remove("rtl")
			}
		}
	}

	/**
	 * Initialize locale on component mount
	 * When online, fetches language from server; when offline, uses cache
	 */
	async function initLocale() {
		// First, apply cached language immediately (prevents flicker)
		const cachedLocale = detectCachedLanguage()
		applyLocale(cachedLocale)

		// Load cached allowed locales first for immediate display
		const cachedAllowed = getCachedAllowedLocales()
		if (cachedAllowed) {
			allowedLocales.value = cachedAllowed
		}

		// If online and haven't fetched from server yet, get server language
		if (!offlineState.isOffline && !serverLanguageFetched) {
			serverLanguageFetched = true

			// Fetch allowed locales from server
			const serverAllowed = await fetchAllowedLocalesFromServer()
			if (serverAllowed) {
				allowedLocales.value = serverAllowed
			}

			const serverLocale = await fetchLanguageFromServer()

			// If server returned a different language, switch to it
			if (serverLocale && serverLocale !== cachedLocale) {
				log.info(`Server language (${serverLocale}) differs from cached (${cachedLocale}), switching`)
				await changeLocale(serverLocale)
			}
		}
	}

	// Auto-initialize on first mount
	onMounted(() => {
		initLocale()
	})

	// Build supported locales with flag URLs, filtered by allowed locales from POS Settings
	const supportedLocales = computed(() => {
		const result = {}
		const allowed = allowedLocales.value

		for (const [code, config] of Object.entries(SUPPORTED_LOCALES)) {
			// If allowed locales are set, filter by them; otherwise show all
			if (allowed === null || allowed.length === 0 || allowed.includes(code)) {
				result[code] = {
					...config,
					flagUrl: getFlagUrl(config.countryCode),
					flagUrlSvg: getFlagUrlSvg(config.countryCode),
				}
			}
		}
		return result
	})

	return {
		locale,
		dir,
		isRTL,
		localeConfig,
		supportedLocales,
		changeLocale,
		initLocale,
		translationVersion, // Used to trigger re-renders when translations change
	}
}
