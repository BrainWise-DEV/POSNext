<template>
	<div class="bg-white dark:bg-gray-800 h-full flex flex-col">
		<!-- Header -->
		<div class="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
			<h2 class="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
				<FeatherIcon name="user-plus" class="w-5 h-5 text-blue-600 dark:text-blue-400" />
				{{ __("My Information") }}
			</h2>
			<button
				class="p-1 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
				@click="$emit('close')"
			>
				<FeatherIcon name="x" class="w-5 h-5" />
			</button>
		</div>

		<!-- Form -->
		<form class="flex-1 p-4 space-y-4 overflow-y-auto" @submit.prevent="handleSubmit">
			<!-- Error message -->
			<div v-if="error" class="p-3 bg-red-100 dark:bg-red-900/50 border border-red-300 dark:border-red-700 rounded-lg">
				<p class="text-red-700 dark:text-red-300 text-sm">{{ error }}</p>
			</div>

			<!-- First Name and Last Name -->
			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-1">
					<label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
						{{ __("Your First Name") }} <span class="text-red-500 dark:text-red-400">*</span>
					</label>
					<input
						v-model="form.first_name"
						type="text"
						required
						:placeholder="__('First name')"
						class="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
						:disabled="isSubmitting"
					/>
				</div>
				<div class="space-y-1">
					<label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
						{{ __("Your Last Name") }} <span class="text-red-500 dark:text-red-400">*</span>
					</label>
					<input
						v-model="form.last_name"
						type="text"
						required
						:placeholder="__('Last name')"
						class="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
						:disabled="isSubmitting"
					/>
				</div>
			</div>

			<!-- Email -->
			<div class="space-y-1">
				<label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
					{{ __("Email") }}
				</label>
				<input
					v-model="form.email"
					type="email"
					:placeholder="__('customer@example.com')"
					class="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
					:disabled="isSubmitting"
				/>
			</div>

			<!-- Mobile Number with Country Code Selector -->
			<div class="space-y-1">
				<label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
					{{ __("Mobile Number") }}
				</label>
				<div class="flex gap-2">
					<!-- Country Code Dropdown -->
					<div class="relative" ref="dropdownRef">
						<button
							type="button"
							@click="showCountryDropdown = !showCountryDropdown"
							class="flex items-center gap-1 w-24 ps-2 pe-1 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-50 dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-900 dark:text-white"
							:disabled="isSubmitting"
						>
							<img
								:src="`https://flagcdn.com/h24/${currentCountryCode}.png`"
								:alt="currentCountryCode"
								class="w-6 h-auto rounded-sm"
								@error="handleFlagError"
							/>
							<span class="flex-1 text-start">{{ selectedCountryCode || "+33" }}</span>
							<svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
							</svg>
						</button>

						<!-- Country Search Dropdown -->
						<div
							v-if="showCountryDropdown"
							class="absolute start-0 z-50 mt-1 w-72 max-h-64 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-600 overflow-hidden"
						>
							<div class="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-600 p-2">
								<input
									ref="countrySearchRef"
									v-model="countrySearchQuery"
									type="text"
									:placeholder="__('Search country...')"
									class="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
									@keydown.escape="showCountryDropdown = false"
								/>
							</div>
							<div class="overflow-y-auto max-h-48">
								<button
									v-for="country in filteredCountries"
									:key="country.code"
									type="button"
									@click="selectCountry(country)"
									class="w-full flex items-center gap-3 px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-start"
									:class="{ 'bg-blue-50 dark:bg-blue-900/30': selectedCountryCode === country.isd }"
								>
									<img
										:src="`https://flagcdn.com/h24/${country.code.toLowerCase()}.png`"
										:alt="country.name"
										class="w-5 h-auto rounded-sm shadow-sm"
										@error="(e) => (e.target.style.display = 'none')"
									/>
									<span class="flex-1 text-sm text-gray-700 dark:text-gray-300 truncate">{{ country.name }}</span>
									<span class="text-sm text-gray-500 dark:text-gray-400">{{ country.isd }}</span>
								</button>
								<div v-if="filteredCountries.length === 0" class="px-4 py-6 text-center text-sm text-gray-500 dark:text-gray-400">
									{{ __("No countries found") }}
								</div>
							</div>
						</div>
					</div>

					<!-- Phone Number Input -->
					<input
						v-model="phoneNumber"
						type="tel"
						:placeholder="__('Phone number')"
						class="flex-1 px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent text-start"
						:disabled="isSubmitting"
						@input="updateMobileNumber"
					/>
				</div>
			</div>

			<!-- Address fields (conditional) -->
			<template v-if="showAddress">
				<!-- Address Line 1 -->
				<div class="space-y-1">
					<label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
						{{ __("Address") }}
					</label>
					<input
						v-model="form.address_line1"
						type="text"
						:placeholder="__('Street address')"
						class="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
						:disabled="isSubmitting"
					/>
				</div>

				<!-- City and Postal Code -->
				<div class="grid grid-cols-2 gap-3">
					<div class="space-y-1">
						<label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
							{{ __("City") }}
						</label>
						<input
							v-model="form.city"
							type="text"
							:placeholder="__('City')"
							class="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
							:disabled="isSubmitting"
						/>
					</div>
					<div class="space-y-1">
						<label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
							{{ __("Postal Code") }}
						</label>
						<input
							v-model="form.pincode"
							type="text"
							:placeholder="__('Postal code')"
							class="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
							:disabled="isSubmitting"
						/>
					</div>
				</div>

				<!-- Country -->
				<div class="space-y-1">
					<label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
						{{ __("Country") }}
					</label>
					<input
						v-model="form.country"
						type="text"
						:placeholder="__('Country')"
						class="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
						:disabled="isSubmitting"
					/>
				</div>
			</template>
		</form>

		<!-- Footer -->
		<div class="p-4 border-t border-gray-200 dark:border-gray-700 space-y-3">
			<button
				:disabled="isSubmitting || !form.first_name || !form.last_name"
				class="w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 dark:disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg font-medium text-white transition-colors flex items-center justify-center gap-2"
				@click="handleSubmit"
			>
				<FeatherIcon
					v-if="isSubmitting"
					name="loader"
					class="w-4 h-4 animate-spin"
				/>
				<span>{{ isSubmitting ? __("Submitting...") : __("Submit") }}</span>
			</button>

			<button
				type="button"
				:disabled="isSubmitting"
				class="w-full py-2 px-4 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50 rounded-lg font-medium text-gray-700 dark:text-gray-300 transition-colors"
				@click="$emit('close')"
			>
				{{ __("Cancel") }}
			</button>
		</div>
	</div>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"
import {
	reactive,
	ref,
	computed,
	onMounted,
	onBeforeUnmount,
	nextTick,
	watch,
} from "vue"
import { useCustomerDisplayStore } from "@/stores/customerDisplay"
import { useCountriesStore } from "@/stores/countries"

const props = defineProps({
	showAddress: {
		type: Boolean,
		default: true,
	},
})

const emit = defineEmits(["close", "created"])

const displayStore = useCustomerDisplayStore()
const countriesStore = useCountriesStore()

// Get default country from session (company country)
const defaultCountry = displayStore.sessionInfo?.country || ""

const form = reactive({
	first_name: "",
	last_name: "",
	email: "",
	mobile_no: "",
	// Address fields
	address_line1: "",
	city: "",
	pincode: "",
	country: defaultCountry,
})

// Phone number with country code
const selectedCountryCode = ref("")
const phoneNumber = ref("")
const showCountryDropdown = ref(false)
const countrySearchQuery = ref("")
const dropdownRef = ref(null)
const countrySearchRef = ref(null)

const isSubmitting = ref(false)
const error = ref(null)

// Computed for country code display
const currentCountryCode = computed(() => {
	const country = countriesStore.countries.find(
		(c) => c.isd === selectedCountryCode.value,
	)
	return country?.code.toLowerCase() || "fr"
})

const filteredCountries = computed(() => {
	if (!countrySearchQuery.value) return countriesStore.countries

	const query = countrySearchQuery.value.toLowerCase()
	return countriesStore.countries.filter(
		(c) =>
			c.name.toLowerCase().includes(query) ||
			c.isd.includes(query) ||
			c.code.toLowerCase().includes(query),
	)
})

// Set country code from country name
function setCountryFromName(countryName) {
	if (!countryName) {
		selectedCountryCode.value = "+33"
		return
	}

	const isd = countriesStore.countryNameToISDMap[countryName]
	if (isd) {
		selectedCountryCode.value = isd
	} else {
		selectedCountryCode.value = "+33"
	}
}

// Country dropdown handlers
function handleFlagError(e) {
	e.target.style.display = "none"
}

function selectCountry(country) {
	selectedCountryCode.value = country.isd
	showCountryDropdown.value = false
	countrySearchQuery.value = ""
	updateMobileNumber()
}

function updateMobileNumber() {
	form.mobile_no = phoneNumber.value
		? `${selectedCountryCode.value}-${phoneNumber.value}`
		: ""
}

function handleClickOutside(event) {
	if (dropdownRef.value && !dropdownRef.value.contains(event.target)) {
		showCountryDropdown.value = false
		countrySearchQuery.value = ""
	}
}

// Watch for dropdown open to focus search
watch(showCountryDropdown, async (isOpen) => {
	if (isOpen) {
		await nextTick()
		countrySearchRef.value?.focus()
	}
})

// Load countries on mount
onMounted(async () => {
	await countriesStore.loadCountries()
	// Set default country code from company country
	if (defaultCountry) {
		setCountryFromName(defaultCountry)
	}
	document.addEventListener("click", handleClickOutside)
})

onBeforeUnmount(() => {
	document.removeEventListener("click", handleClickOutside)
})

async function handleSubmit() {
	if (!form.first_name || !form.last_name) return

	isSubmitting.value = true
	error.value = null

	try {
		const customerData = {
			customer_name: `${form.first_name.trim()} ${form.last_name.trim()}`,
			email: form.email.trim() || null,
			mobile_no: form.mobile_no.trim() || null,
		}

		// Add address fields if provided
		if (props.showAddress) {
			if (form.address_line1.trim())
				customerData.address_line1 = form.address_line1.trim()
			if (form.city.trim()) customerData.city = form.city.trim()
			if (form.pincode.trim()) customerData.pincode = form.pincode.trim()
			if (form.country.trim()) customerData.country = form.country.trim()
		}

		const customer = await displayStore.createCustomer(customerData)

		// Reset form (keep default country and country code)
		form.first_name = ""
		form.last_name = ""
		form.email = ""
		form.mobile_no = ""
		form.address_line1 = ""
		form.city = ""
		form.pincode = ""
		form.country = defaultCountry
		phoneNumber.value = ""

		// Emit created event
		emit("created", customer)
	} catch (err) {
		error.value = err.message || __("An error occurred. Please try again.")
	} finally {
		isSubmitting.value = false
	}
}
</script>
