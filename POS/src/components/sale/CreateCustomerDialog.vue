<template>
	<Dialog v-model="show" :options="{ title: 'Create New Customer', size: 'md' }">
		<template #body-content>
			<div class="space-y-4">
				<!-- Customer Name -->
				<div>
					<label class="block text-sm font-medium text-gray-700 mb-2">
						Customer Name <span class="text-red-500">*</span>
					</label>
					<Input
						v-model="customerData.customer_name"
						type="text"
						placeholder="Enter customer name"
						required
					/>
				</div>

				<!-- Mobile Number with Country Code -->
				<div>
					<label class="block text-sm font-medium text-gray-700 mb-2">
						Mobile Number
					</label>
					<div class="flex gap-2">
						<!-- Country Code Searchable Dropdown -->
						<div class="relative" ref="dropdownRef">
							<button
								type="button"
								@click="showCountryDropdown = !showCountryDropdown"
								class="flex items-center gap-1 w-24 pl-2 pr-1 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white hover:bg-gray-50"
							>
								<img
									:src="`https://flagcdn.com/h24/${currentCountryCode}.png`"
									:alt="currentCountryCode"
									class="w-6 h-auto rounded-sm"
									@error="handleFlagError"
								/>
								<span class="flex-1 text-left">{{ selectedCountryCode || "+20" }}</span>
								<svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
								</svg>
							</button>

							<!-- Dropdown Menu -->
							<div
								v-if="showCountryDropdown"
								class="absolute left-0 z-50 mt-1 w-80 max-h-80 bg-white rounded-lg shadow-lg border border-gray-200 overflow-hidden"
							>
								<!-- Search Input -->
								<div class="sticky top-0 bg-white border-b border-gray-200 p-2">
									<input
										ref="countrySearchRef"
										v-model="countrySearchQuery"
										type="text"
										placeholder="Search country or code..."
										class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
										@keydown.escape="showCountryDropdown = false"
									/>
								</div>

								<!-- Countries List -->
								<div class="overflow-y-auto max-h-64">
									<button
										v-for="country in filteredCountries"
										:key="country.code"
										type="button"
										@click="selectCountry(country)"
										class="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-gray-50 transition-colors text-left"
										:class="{ 'bg-blue-50': selectedCountryCode === country.isd }"
									>
										<img
											:src="`https://flagcdn.com/h24/${country.code.toLowerCase()}.png`"
											:alt="country.name"
											class="w-6 h-auto rounded-sm shadow-sm"
											@error="(e) => (e.target.style.display = 'none')"
										/>
										<span class="flex-1 text-sm font-medium text-gray-700">{{ country.name }}</span>
										<span class="text-sm text-gray-500">{{ country.isd }}</span>
									</button>
									<div v-if="filteredCountries.length === 0" class="px-4 py-8 text-center text-sm text-gray-500">
										No countries found
									</div>
								</div>
							</div>
						</div>

						<!-- Phone Number Input -->
						<input
							v-model="phoneNumber"
							type="tel"
							placeholder="Enter phone number"
							class="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
							@input="updateMobileNumber"
						/>
					</div>
				</div>

				<!-- Email -->
				<div>
					<label class="block text-sm font-medium text-gray-700 mb-2">
						Email
					</label>
					<Input
						v-model="customerData.email_id"
						type="email"
						placeholder="Enter email address"
					/>
				</div>

				<!-- Customer Group -->
				<div>
					<label class="block text-sm font-medium text-gray-700 mb-2">
						Customer Group
					</label>
					<select
						v-model="customerData.customer_group"
						class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
					>
						<option value="">Select Customer Group</option>
						<option v-for="group in customerGroups" :key="group" :value="group">
							{{ group }}
						</option>
					</select>
				</div>

				<!-- Territory -->
				<div>
					<label class="block text-sm font-medium text-gray-700 mb-2">
						Territory
					</label>
					<select
						v-model="customerData.territory"
						class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
					>
						<option value="">Select Territory</option>
						<option v-for="territory in territories" :key="territory" :value="territory">
							{{ territory }}
						</option>
					</select>
				</div>
			</div>
		</template>

		<template #actions>
			<div class="flex flex-col space-y-2">
				<!-- Permission Warning -->
				<div v-if="!hasPermission" class="px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg">
					<div class="flex items-start space-x-2">
						<svg class="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
							<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
						</svg>
						<div class="flex-1">
							<p class="text-sm font-medium text-amber-900">Permission Required</p>
							<p class="text-xs text-amber-700 mt-0.5">You don't have permission to create customers. Contact your administrator.</p>
						</div>
					</div>
				</div>

				<div class="flex space-x-2">
					<Button variant="subtle" @click="show = false">
						Cancel
					</Button>
					<Button
						variant="solid"
						@click="handleCreate"
						:loading="createCustomerResource.loading || checkingPermission"
						:disabled="!customerData.customer_name || !hasPermission"
					>
						Create Customer
					</Button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { usePOSPermissions } from "@/composables/usePermissions"
import { useToast } from "@/composables/useToast"
import { useCountriesStore } from "@/stores/countries"
import { logger } from "@/utils/logger"
import { Button, Dialog, Input, createResource } from "frappe-ui"
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"

const log = logger.create("CreateCustomerDialog")

// Stores
const countriesStore = useCountriesStore()
const { canCreateCustomer } = usePOSPermissions()
const { showSuccess, showError } = useToast()

// Load countries immediately during setup (before mount)
countriesStore.loadCountries()

// Props & Emits
const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
	initialName: String,
})
const emit = defineEmits(["update:modelValue", "customer-created"])

// State
const hasPermission = ref(true)
const checkingPermission = ref(false)
const selectedCountryCode = ref("")
const phoneNumber = ref("")
const showCountryDropdown = ref(false)
const countrySearchQuery = ref("")
const dropdownRef = ref(null)
const countrySearchRef = ref(null)

// Computed
const show = computed({
	get: () => props.modelValue,
	set: (val) => emit("update:modelValue", val),
})

const currentCountryCode = computed(() => {
	const country = countriesStore.countries.find((c) => c.isd === selectedCountryCode.value)
	return country?.code.toLowerCase() || "eg"
})

const filteredCountries = computed(() => {
	if (!countrySearchQuery.value) return countriesStore.countries

	const query = countrySearchQuery.value.toLowerCase()
	return countriesStore.countries.filter(
		(c) =>
			c.name.toLowerCase().includes(query) ||
			c.isd.includes(query) ||
			c.code.toLowerCase().includes(query)
	)
})

// Methods
const handleFlagError = (e) => (e.target.style.display = "none")

const selectCountry = (country) => {
	selectedCountryCode.value = country.isd
	showCountryDropdown.value = false
	countrySearchQuery.value = ""
	updateMobileNumber()
	// Territory will be updated by the watcher automatically
}

const updateMobileNumber = () => {
	customerData.value.mobile_no = phoneNumber.value
		? `${selectedCountryCode.value}-${phoneNumber.value}`
		: ""
}

const handleClickOutside = (event) => {
	if (dropdownRef.value && !dropdownRef.value.contains(event.target)) {
		showCountryDropdown.value = false
		countrySearchQuery.value = ""
	}
}

const setCountryFromName = (countryName) => {
	if (!countryName) {
		selectedCountryCode.value = "+20"
		return
	}

	const isd = countriesStore.countryNameToISDMap[countryName]
	if (isd) {
		selectedCountryCode.value = isd
		log.info(`Set country code to ${isd} for ${countryName}`)
	} else {
		log.warn(`Country "${countryName}" not found in map`, {
			available: Object.keys(countriesStore.countryNameToISDMap).slice(0, 10),
		})
		selectedCountryCode.value = "+20"
	}
}

const updateTerritoryFromCountry = () => {
	if (!territories.value.length) {
		log.debug("No territories loaded yet")
		return
	}

	const country = countriesStore.countries.find((c) => c.isd === selectedCountryCode.value)
	if (!country) {
		log.warn(`No country found for code ${selectedCountryCode.value}`)
		return
	}

	log.info(`Updating territory for ${country.name}`, {
		availableTerritories: territories.value.length,
	})

	// Try exact match first
	if (territories.value.includes(country.name)) {
		customerData.value.territory = country.name
		log.info(`Territory set to exact match: ${country.name}`)
		return
	}

	// Try fuzzy match
	const fuzzyMatch = territories.value.find(
		(t) =>
			t.toLowerCase().includes(country.name.toLowerCase()) ||
			country.name.toLowerCase().includes(t.toLowerCase())
	)

	if (fuzzyMatch) {
		customerData.value.territory = fuzzyMatch
		log.info(`Territory set to fuzzy match: ${fuzzyMatch} for ${country.name}`)
	} else {
		log.warn(`No territory match found for ${country.name}`)
	}
}

const customerGroups = ref([
	"Commercial",
	"Individual",
	"Non Profit",
	"Government",
])
const territories = ref(["All Territories"])

const customerData = ref({
	customer_name: "",
	mobile_no: "",
	email_id: "",
	customer_group: "Individual",
	territory: "All Territories",
})

// Watchers
watch(
	() => props.initialName,
	(name) => name && (customerData.value.customer_name = name)
)

watch(
	() => customerData.value.mobile_no,
	(value) => {
		if (value?.includes("-")) {
			const [code, ...rest] = value.split("-")
			selectedCountryCode.value = code
			phoneNumber.value = rest.join("-")
		}
	}
)

// Watch country code changes and update territory (with slight delay to ensure territories loaded)
watch(selectedCountryCode, async () => {
	await nextTick()
	updateTerritoryFromCountry()
})

watch(showCountryDropdown, async (isOpen) => {
	if (isOpen) {
		await nextTick()
		countrySearchRef.value?.focus()
	}
})

// Create customer resource
const createCustomerResource = createResource({
	url: "frappe.client.insert",
	makeParams() {
		return {
			doc: {
				doctype: "Customer",
				customer_name: customerData.value.customer_name,
				customer_type: "Individual",
				customer_group: customerData.value.customer_group || "Individual",
				territory: customerData.value.territory || "All Territories",
				mobile_no: customerData.value.mobile_no || "",
				email_id: customerData.value.email_id || "",
			},
		}
	},
	onSuccess(data) {
		showSuccess(`Customer ${data.customer_name} created successfully`)

		emit("customer-created", data)
		show.value = false
	},
	onError(error) {
		log.error("Error creating customer", error)
		showError(error.message || "Failed to create customer")
	},
})

// Resources
const createListResource = (doctype, onSuccess) =>
	createResource({
		url: "frappe.client.get_list",
		makeParams: () => ({
			doctype,
			fields: ["name"],
			filters: doctype === "Customer Group" ? { is_group: 0 } : {},
			limit_page_length: 500,
		}),
		auto: false,
		onSuccess: (data) => data?.length && onSuccess(data.map((d) => d.name)),
		onError: (err) => log.error(`Error loading ${doctype}`, err),
	})

const customerGroupsResource = createListResource("Customer Group", (names) => {
	customerGroups.value = names
})

const territoriesResource = createListResource("Territory", (names) => {
	territories.value = names
})

const posProfileResource = createResource({
	url: "frappe.client.get_value",
	makeParams: () => ({
		doctype: "POS Profile",
		filters: { name: props.posProfile },
		fieldname: ["country"],
	}),
	auto: false,
	onSuccess: (data) => setCountryFromName(data?.country || "Egypt"),
	onError: (err) => {
		log.error("Error loading POS Profile", err)
		selectedCountryCode.value = "+20"
	},
})

// Dialog lifecycle
const loadDialogData = async () => {
	// Load territories first (needed for territory matching)
	await territoriesResource.reload()
	customerGroupsResource.reload()
	checkPermissions()

	// Load country from POS Profile after territories are loaded
	if (props.posProfile) {
		await posProfileResource.reload()
	} else {
		selectedCountryCode.value = "+20"
	}
}

watch(() => props.modelValue, async (isOpen) => {
	show.value = isOpen
	isOpen ? await loadDialogData() : resetForm()
})

watch(show, (val) => emit("update:modelValue", val))

// Initialize
onMounted(() => {
	loadDialogData()
	document.addEventListener("click", handleClickOutside)
})

onBeforeUnmount(() => {
	document.removeEventListener("click", handleClickOutside)
})

// Handlers
const checkPermissions = async () => {
	checkingPermission.value = true
	try {
		hasPermission.value = await canCreateCustomer()
	} catch (err) {
		log.error("Permission check failed", err)
		hasPermission.value = false
	} finally {
		checkingPermission.value = false
	}
}

const handleCreate = async () => {
	if (!customerData.value.customer_name) return showError("Customer Name is required")
	await createCustomerResource.submit()
}

const resetForm = () => {
	Object.assign(customerData.value, {
		customer_name: "",
		mobile_no: "",
		email_id: "",
		customer_group: "Individual",
		territory: "All Territories",
	})
	selectedCountryCode.value = ""
	phoneNumber.value = ""
}
</script>

<style scoped>
.sr-only {
	position: absolute;
	width: 1px;
	height: 1px;
	padding: 0;
	margin: -1px;
	overflow: hidden;
	clip: rect(0, 0, 0, 0);
	white-space: nowrap;
	border-width: 0;
}
</style>
