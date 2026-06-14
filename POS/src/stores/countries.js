import { createResource } from "frappe-ui"
import { defineStore } from "pinia"
import { computed, ref } from "vue"
import { logger } from "@/utils/logger"

const log = logger.create("CountriesStore")

export const useCountriesStore = defineStore("countries", () => {
	// State
	const countries = ref([])
	const loading = ref(false)
	const loaded = ref(false)

	// Resource for fetching countries
	const countriesResource = createResource({
		url: "frappe.geo.country_info.get_country_timezone_info",
		auto: false,
		onSuccess(data) {
			if (data?.country_info) {
				countries.value = formatCountries(data.country_info)
				loaded.value = true
				log.info(`Loaded ${countries.value.length} countries`)
			}
		},
		onError(error) {
			log.error("Error loading country codes", error)
		},
	})

	// Format countries for dropdown use
	function formatCountries(countryInfo) {
		return Object.entries(countryInfo)
			.filter(([_, info]) => info.isd) // Only countries with ISD codes
			.map(([name, info]) => ({
				name,
				code: info.code?.toUpperCase() || "",
				isd: info.isd,
				flagUrl: `https://flagcdn.com/h24/${info.code}.png`, // Higher quality 24px height
				flagUrlSvg: `https://flagcdn.com/${info.code}.svg`, // Vector format
				flagEmoji: getCountryFlagEmoji(info.code),
			}))
			.sort((a, b) => a.name.localeCompare(b.name))
	}

	// Convert country code to flag emoji
	function getCountryFlagEmoji(countryCode) {
		if (!countryCode) return "🏳️"

		const code = countryCode.toUpperCase()
		const codePoints = [...code].map((char) => 127397 + char.charCodeAt(0))
		return String.fromCodePoint(...codePoints)
	}

	// Load countries (only once)
	async function loadCountries() {
		if (loaded.value) {
			log.debug("Countries already loaded from cache")
			return countries.value
		}

		if (loading.value) {
			log.debug("Countries already loading, waiting...")
			// Wait for existing load to complete
			await new Promise((resolve) => {
				const checkLoaded = setInterval(() => {
					if (!loading.value) {
						clearInterval(checkLoaded)
						resolve()
					}
				}, 50)
			})
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

	// Validate phone number format
	function validatePhoneNumber(phoneNumber) {
		if (!phoneNumber) return true
		const cleanNumber = phoneNumber.replace(/\D/g, "")
		return cleanNumber.length >= 7 && cleanNumber.length <= 15
	}

	// Computed
	const countryNameToISDMap = computed(() =>
		Object.fromEntries(countries.value.map((c) => [c.name, c.isd]))
	)

	return {
		// State
		countries: computed(() => countries.value),
		loading: computed(() => loading.value),
		loaded: computed(() => loaded.value),

		// Computed
		countryNameToISDMap,

		// Actions
		loadCountries,
		findCountryByISD,
		findCountryByName,
		findCountryByCode,
		formatPhoneNumber,
		parsePhoneNumber,
		validatePhoneNumber,
		getCountryFlagEmoji,
	}
})
