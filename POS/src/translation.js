import { createResource } from "frappe-ui"

export default function translationPlugin(app) {
	app.config.globalProperties.__ = translate
	app.config.globalProperties.$changeLanguage = changeLanguage
	window.__ = translate
	window.$changeLanguage = changeLanguage
	if (!window.translatedMessages) fetchTranslations()
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

function fetchTranslations(language = null) {
	const params = language ? { language } : {}
	createResource({
		url: "pos_next.api.get_translations",
		params,
		cache: language ? undefined : "translations",
		auto: true,
		transform: (data) => {
			window.translatedMessages = data
		},
	})
}

export function changeLanguage(language) {
	// Store language preference in localStorage
	localStorage.setItem("preferredLanguage", language)

	// Fetch new translations
	return createResource({
		url: "pos_next.api.get_translations",
		params: { language },
		auto: true,
		transform: (data) => {
			window.translatedMessages = data
			// Set document direction for RTL languages
			const rtlLanguages = ["ar", "he", "fa", "ur"]
			document.documentElement.dir = rtlLanguages.includes(language) ? "rtl" : "ltr"
			document.documentElement.lang = language
		},
	})
}
