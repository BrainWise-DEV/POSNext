<template>
	<div class="relative" ref="selectorRef">
		<!-- Country Code Button -->
		<button
			type="button"
			@click="toggleDropdown"
			class="flex items-center gap-1.5 px-3 py-2 border border-gray-300 rounded-l-lg bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors h-full"
			:class="{ 'opacity-50 cursor-not-allowed': disabled }"
			:disabled="disabled"
		>
			<!-- Flag -->
			<div class="w-5 h-4 flex items-center justify-center flex-shrink-0">
				<img
					v-if="selectedCountry"
					:src="selectedCountry.flagUrl"
					:alt="selectedCountry.name"
					class="w-5 h-auto rounded-sm"
					@error="handleImageError"
				/>
				<span v-else-if="selectedCountry" class="text-base leading-none">
					{{ selectedCountry.flagEmoji }}
				</span>
				<svg v-else class="w-4 h-4 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
					<path
						fill-rule="evenodd"
						d="M10 18a8 8 0 100-16 8 8 0 000 16zM4.332 8.027a6.012 6.012 0 011.912-2.706C6.512 5.73 6.974 6 7.5 6A1.5 1.5 0 019 7.5V8a2 2 0 004 0 2 2 0 011.523-1.943A5.977 5.977 0 0116 10c0 .34-.028.675-.083 1H15a2 2 0 00-2 2v2.197A5.973 5.973 0 0110 16v-2a2 2 0 00-2-2 2 2 0 01-2-2 2 2 0 00-1.668-1.973z"
						clip-rule="evenodd"
					/>
				</svg>
			</div>

			<!-- ISD Code -->
			<span class="text-sm font-medium text-gray-700 min-w-[3rem] text-start">
				{{ selectedCountry?.isd || "+1" }}
			</span>

			<!-- Dropdown Arrow -->
			<svg
				class="w-4 h-4 text-gray-500 transition-transform"
				:class="{ 'rotate-180': isOpen }"
				fill="none"
				stroke="currentColor"
				viewBox="0 0 24 24"
			>
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
			</svg>
		</button>

		<!-- Dropdown Menu -->
		<Transition
			enter-active-class="transition ease-out duration-100"
			enter-from-class="transform opacity-0 scale-95"
			enter-to-class="transform opacity-100 scale-100"
			leave-active-class="transition ease-in duration-75"
			leave-from-class="transform opacity-100 scale-100"
			leave-to-class="transform opacity-0 scale-95"
		>
			<div
				v-if="isOpen"
				class="absolute start-0 z-50 mt-1 w-80 max-h-80 bg-white rounded-lg shadow-lg border border-gray-200 overflow-hidden"
				:style="{ top: dropdownPosition }"
			>
				<!-- Search Input -->
				<div class="sticky top-0 bg-white border-b border-gray-200 p-3">
					<div class="relative">
						<input
							ref="searchInputRef"
							v-model="searchQuery"
							type="text"
							:placeholder="__('Search countries...')"
							class="w-full ps-9 pe-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
							@keydown.escape="closeDropdown"
							@keydown.enter.prevent="selectFirstFiltered"
						/>
						<svg
							class="absolute start-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
							/>
						</svg>
					</div>
				</div>

				<!-- Countries List -->
				<div class="overflow-y-auto max-h-64">
					<div v-if="loading" class="flex items-center justify-center py-8">
						<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
					</div>

					<div v-else-if="filteredCountries.length === 0" class="px-4 py-8 text-center text-sm text-gray-500">
						{{ __('No countries found') }}
					</div>

					<button
						v-for="country in filteredCountries"
						:key="country.code"
						type="button"
						@click="selectCountry(country)"
						class="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 transition-colors text-start"
						:class="{
							'bg-blue-50 hover:bg-blue-100': selectedCountry?.code === country.code,
						}"
					>
						<!-- Flag -->
						<div class="w-6 h-4 flex items-center justify-center flex-shrink-0">
							<img
								:src="country.flagUrl"
								:alt="country.name"
								class="w-6 h-auto rounded-sm"
								@error="(e) => (e.target.style.display = 'none')"
							/>
						</div>

						<!-- Country Name -->
						<span class="flex-1 text-sm font-medium text-gray-700">
							{{ country.name }}
						</span>

						<!-- ISD Code -->
						<span class="text-sm text-gray-500 font-mono">
							{{ country.isd }}
						</span>
					</button>
				</div>
			</div>
		</Transition>
	</div>
</template>

<script setup>
import { useCountryCodes } from "@/composables/useCountryCodes"
import { computed, onMounted, ref, watch, nextTick } from "vue"

const props = defineProps({
	modelValue: {
		type: String,
		default: "",
	},
	disabled: {
		type: Boolean,
		default: false,
	},
	defaultCountry: {
		type: String,
		default: "United States", // Default to US
	},
})

const emit = defineEmits(["update:modelValue", "country-change"])

const {
	countries,
	loading,
	loadCountries,
	findCountryByISD,
	findCountryByName,
	findCountryByCode,
} = useCountryCodes()

const isOpen = ref(false)
const searchQuery = ref("")
const selectedCountry = ref(null)
const selectorRef = ref(null)
const searchInputRef = ref(null)
const dropdownPosition = ref("100%")

// Filter countries based on search
const filteredCountries = computed(() => {
	if (!searchQuery.value) return countries.value

	const query = searchQuery.value.toLowerCase()
	return countries.value.filter(
		(country) =>
			country.name.toLowerCase().includes(query) ||
			country.isd.includes(query) ||
			country.code.toLowerCase().includes(query)
	)
})

// Toggle dropdown
function toggleDropdown() {
	if (props.disabled) return
	isOpen.value = !isOpen.value
	if (isOpen.value) {
		nextTick(() => {
			searchInputRef.value?.focus()
		})
	}
}

// Close dropdown
function closeDropdown() {
	isOpen.value = false
	searchQuery.value = ""
}

// Select country
function selectCountry(country) {
	selectedCountry.value = country
	emit("update:modelValue", country.isd)
	emit("country-change", country)
	closeDropdown()
}

// Select first filtered country (when pressing Enter in search)
function selectFirstFiltered() {
	if (filteredCountries.value.length > 0) {
		selectCountry(filteredCountries.value[0])
	}
}

// Handle flag image load error
function handleImageError(event) {
	// Hide broken image and show emoji fallback
	event.target.style.display = "none"
}

// Close dropdown when clicking outside
function handleClickOutside(event) {
	if (selectorRef.value && !selectorRef.value.contains(event.target)) {
		closeDropdown()
	}
}

// Watch for external value changes
watch(
	() => props.modelValue,
	(newValue) => {
		if (newValue && newValue !== selectedCountry.value?.isd) {
			const country = findCountryByISD(newValue)
			if (country) {
				selectedCountry.value = country
			}
		}
	}
)

// Initialize
onMounted(async () => {
	await loadCountries()

	// Set initial country
	if (props.modelValue) {
		const country = findCountryByISD(props.modelValue)
		if (country) {
			selectedCountry.value = country
		}
	} else if (props.defaultCountry) {
		// Try to find default country by name or code
		const country =
			findCountryByName(props.defaultCountry) || findCountryByCode(props.defaultCountry)
		if (country) {
			selectedCountry.value = country
			emit("update:modelValue", country.isd)
			emit("country-change", country)
		}
	}

	// Add click outside listener
	document.addEventListener("click", handleClickOutside)
})

// Cleanup
import { onBeforeUnmount } from "vue"
onBeforeUnmount(() => {
	document.removeEventListener("click", handleClickOutside)
})
</script>

<style scoped>
/* Custom scrollbar for dropdown */
.overflow-y-auto::-webkit-scrollbar {
	width: 6px;
}

.overflow-y-auto::-webkit-scrollbar-track {
	background: #f1f1f1;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
	background: #cbd5e0;
	border-radius: 3px;
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
	background: #a0aec0;
}
</style>
