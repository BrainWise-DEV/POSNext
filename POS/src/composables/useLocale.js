import { ref, computed, onMounted } from "vue"

// Reactive locale state (shared across all components)
const currentLocale = ref("en")
const currentDir = ref("ltr")
const PREFARED_LANGUAGE_KEY = "pos_next_language"

// Supported languages configuration
export const SUPPORTED_LOCALES = {
	en: {
		name: "English",
		nativeName: "English",
		flag: "🇺🇸",
		dir: "ltr",
	},
	ar: {
		name: "Arabic",
		nativeName: "العربية",
		flag: "🇸🇦",
		dir: "rtl",
	}
}

/**
 * Detect current language from Frappe boot, localStorage, or browser
 * @returns {string} Language code
 */
function detectLanguage() {
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
	const localeConfig = computed(
		() => SUPPORTED_LOCALES[locale.value] || SUPPORTED_LOCALES.en,
	)

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

		// Use the translation system's changeLanguage function
		if (typeof window !== "undefined" && window.$changeLanguage) {
			try {
				await window.$changeLanguage(newLocale)
			} catch (error) {
				console.error("Failed to change language via translation system:", error)
			}
		}

		// Update Frappe user settings
		if (typeof window !== "undefined" && window.frappe?.call) {
			try {
				await window.frappe.call({
					method: "frappe.client.set_value",
					args: {
						doctype: "User",
						name: window.frappe.session.user,
						fieldname: "language",
						value: newLocale.toLowerCase(),
					},
					freeze: false,
				})
			} catch (error) {
				console.error("Failed to save language preference to Frappe:", error)
			}
		}
	}

	/**
	 * Initialize locale on component mount
	 * Detects language and applies document attributes
	 */
	function initLocale() {
		const detected = detectLanguage()
		currentLocale.value = detected

		const config = SUPPORTED_LOCALES[detected]
		currentDir.value = config.dir

		// Set document attributes
		if (typeof document !== "undefined") {
			document.documentElement.setAttribute("dir", config.dir)
			document.documentElement.setAttribute("lang", detected)

			if (config.dir === "rtl") {
				document.documentElement.classList.add("rtl")
			} else {
				document.documentElement.classList.remove("rtl")
			}
		}
	}

	// Auto-initialize on first mount
	onMounted(() => {
		initLocale()
	})

	return {
		locale,
		dir,
		isRTL,
		localeConfig,
		supportedLocales: SUPPORTED_LOCALES,
		changeLocale,
		initLocale,
	}
}
