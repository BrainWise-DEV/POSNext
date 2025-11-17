import { createResource } from "frappe-ui"

export default function translationPlugin(app) {
	app.config.globalProperties.__ = translate
	app.config.globalProperties.$changeLanguage = changeLanguage
	app.config.globalProperties.$getAvailableLanguages = getAvailableLanguages
	app.config.globalProperties.$isRTL = isRTL
	app.config.globalProperties.$initTranslations = fetchTranslations
	window.__ = translate
	window.$changeLanguage = changeLanguage
	window.$getAvailableLanguages = getAvailableLanguages
	window.$isRTL = isRTL
	window.$initTranslations = fetchTranslations

	// Initialize empty translations
	if (!window.translatedMessages) {
		window.translatedMessages = {}
	}

	// Auto-load translations for guest users (no CSRF required)
	// For logged-in users, translations will be loaded via $initTranslations after CSRF is ready
	if (!window.frappe?.session?.user || window.frappe.session.user === "Guest") {
		fetchTranslations()
	}
}

function translate(message) {
	let translatedMessages = window.translatedMessages || {}
	let translatedMessage = translatedMessages[message] || message

	const hasPlaceholders = /{\d+}/.test(message)
	if (!hasPlaceholders) {
		return translatedMessage
	}
	return {
		format: function (...args) {
			return translatedMessage.replace(/{(\d+)}/g, function (match, number) {
				return typeof args[number] != "undefined" ? args[number] : match
			})
		},
	}
}

function fetchTranslations(langCode = null) {
	// Determine language code
	let language = langCode
	if (!language) {
		if (window.frappe?.session?.user && window.frappe.session.user !== "Guest") {
			language = window.frappe.boot?.user?.language || "en"
		} else {
			language = localStorage.getItem("guestLanguage") || "en"
		}
	}

	// English is default, no need to fetch
	if (language === "en") {
		window.translatedMessages = {}
		setDocumentDirection("en")
		return Promise.resolve({})
	}

	// Fetch translations using GET method (no CSRF required for guest users)
	const resource = createResource({
		url: "pos_next.api.translations.get_translation_dict",
		method: "GET",
		params: { lang_code: language },
		auto: true,
		transform: (data) => {
			window.translatedMessages = data || {}
			setDocumentDirection(language)
			return data
		},
	})

	return resource.promise || Promise.resolve({})
}

export function getAvailableLanguages() {
	return createResource({
		url: "pos_next.api.translations.get_available_languages",
		method: "GET",
		cache: "available_languages",
		auto: true,
	})
}

export function isRTL(langCode = null) {
	const rtlLanguages = ["ar", "he", "fa", "ur"]
	const language = langCode || localStorage.getItem("guestLanguage") || "en"
	return rtlLanguages.includes(language)
}

function setDocumentDirection(language) {
	const rtlLanguages = ["ar", "he", "fa", "ur"]
	const isRtl = rtlLanguages.includes(language)

	document.documentElement.dir = isRtl ? "rtl" : "ltr"
	document.documentElement.lang = language

	if (isRtl) {
		document.body.classList.add("rtl")
	} else {
		document.body.classList.remove("rtl")
	}
}

export async function changeLanguage(langCode) {
	// For guest users, just load translations without saving to backend
	if (!window.frappe?.session?.user || window.frappe.session.user === "Guest") {
		localStorage.setItem("guestLanguage", langCode)
		await fetchTranslations(langCode)
		// Reload page to apply changes
		setTimeout(() => window.location.reload(), 300)
		return { success: true, language: langCode }
	}

	// For logged-in users, save to database (requires authentication, CSRF token available)
	const resource = createResource({
		url: "pos_next.api.translations.set_user_language",
		method: "POST",
		params: { lang_code: langCode },
		auto: true,
		transform: (data) => {
			if (data.success) {
				fetchTranslations(langCode)
				// Reload page to apply changes
				setTimeout(() => window.location.reload(), 300)
			}
			return data
		},
	})

	return resource.promise || Promise.resolve({ success: false })
}
