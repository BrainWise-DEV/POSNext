import { createResource } from "frappe-ui"
import { ref, computed } from "vue"
import { logger } from "@/utils/logger"

const log = logger.create("useCountryCodes")

// Cache the country data globally to avoid multiple API calls
let countriesCache = null
let countriesResource = null

export function useCountryCodes() {
	const countries = ref([])
	const loading = ref(false)

	// Create resource only once
	if (!countriesResource) {
		countriesResource = createResource({
			url: "frappe.geo.country_info.get_country_timezone_info",
			auto: false,
			onSuccess(data) {
				if (data?.country_info) {
					countriesCache = data.country_info
					countries.value = formatCountries(data.country_info)
				}
			},
			onError(error) {
				log.error("Error loading country codes", error)
			},
		})
	}

	// Format countries for dropdown use
	function formatCountries(countryInfo) {
		return Object.entries(countryInfo)
			.filter(([_, info]) => info.isd) // Only countries with ISD codes
			.map(([name, info]) => ({
				name,
				code: info.code?.toUpperCase() || "",
				isd: info.isd,
				flagUrl: `https://flagcdn.com/${info.code}.svg`,
				// Fallback emoji flag using regional indicator symbols
				flagEmoji: getCountryFlagEmoji(info.code),
			}))
			.sort((a, b) => a.name.localeCompare(b.name))
	}

	// Convert country code to flag emoji
	function getCountryFlagEmoji(countryCode) {
		if (!countryCode) return "🏳️"

		const code = countryCode.toUpperCase()
		// Convert country code to regional indicator symbols
		// A=127462, so 'US' becomes 🇺🇸
		const codePoints = [...code].map((char) => 127397 + char.charCodeAt(0))
		return String.fromCodePoint(...codePoints)
	}

	// Load countries if not already cached
	async function loadCountries() {
		if (countriesCache) {
			countries.value = formatCountries(countriesCache)
			return countries.value
		}

		loading.value = true
		try {
			await countriesResource.fetch()
		} finally {
			loading.value = false
		}
		return countries.value
	}

	// Find country by ISD code
	function findCountryByISD(isd) {
		if (!isd) return null
		return countries.value.find((c) => c.isd === isd)
	}

	// Find country by name
	function findCountryByName(name) {
		if (!name) return null
		return countries.value.find((c) => c.name === name)
	}

	// Find country by code
	function findCountryByCode(code) {
		if (!code) return null
		const upperCode = code.toUpperCase()
		return countries.value.find((c) => c.code === upperCode)
	}

	// Format phone number with country code
	function formatPhoneNumber(countryISD, phoneNumber) {
		if (!phoneNumber) return ""
		const cleanNumber = phoneNumber.replace(/\D/g, "")
		return countryISD ? `${countryISD}-${cleanNumber}` : cleanNumber
	}

	// Parse phone number with country code
	function parsePhoneNumber(fullNumber) {
		if (!fullNumber) return { isd: "", number: "" }

		// Check if format is ISD-NUMBER
		if (fullNumber.includes("-")) {
			const [isd, ...rest] = fullNumber.split("-")
			return {
				isd,
				number: rest.join("-"),
			}
		}

		return {
			isd: "",
			number: fullNumber,
		}
	}

	// Validate phone number format (basic validation)
	function validatePhoneNumber(phoneNumber) {
		if (!phoneNumber) return true // Empty is valid (not required by default)

		// Remove all non-digit characters for validation
		const cleanNumber = phoneNumber.replace(/\D/g, "")

		// Phone numbers should be between 7-15 digits (international standard)
		return cleanNumber.length >= 7 && cleanNumber.length <= 15
	}

	return {
		countries: computed(() => countries.value),
		loading: computed(() => loading.value || countriesResource?.loading),
		loadCountries,
		findCountryByISD,
		findCountryByName,
		findCountryByCode,
		formatPhoneNumber,
		parsePhoneNumber,
		validatePhoneNumber,
		getCountryFlagEmoji,
	}
}
