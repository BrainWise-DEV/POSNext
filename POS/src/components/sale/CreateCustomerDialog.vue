<template>
	<Dialog
		v-model="show"
		:options="{
			title: isEditMode ? __('Edit Customer') : __('Create New Customer'),
			size: 'md',
		}"
	>
		<template #body-content>
			<div class="flex flex-col gap-6">
				<!-- Customer Name (Required) — Magento uses first + last name instead -->
				<div v-if="!miraayaCustomerSync">
					<label class="block text-start text-sm font-medium text-gray-700 mb-2">
						{{ __("Customer Name") }} <span class="text-red-500">*</span>
					</label>
					<Input
						v-model="customerData.customer_name"
						type="text"
						:placeholder="__('Enter customer name')"
						required
					/>
				</div>

				<template v-else>
					<div class="grid grid-cols-2 gap-4">
						<div>
							<label class="block text-start text-sm font-medium text-gray-700 mb-2">
								{{ __("First Name") }} <span class="text-red-500">*</span>
							</label>
							<Input
								v-model="customerData.custom_first_name"
								type="text"
								:placeholder="__('First name')"
								required
							/>
						</div>
						<div>
							<label class="block text-start text-sm font-medium text-gray-700 mb-2">
								{{ __("Last Name") }} <span class="text-red-500">*</span>
							</label>
							<Input
								v-model="customerData.custom_last_name"
								type="text"
								:placeholder="__('Last name')"
								required
							/>
						</div>
					</div>
					<div>
						<label class="block text-start text-sm font-medium text-gray-700 mb-2">
							{{ __("Customer Name") }}
						</label>
						<Input
							:model-value="computedCustomerName"
							type="text"
							disabled
							:placeholder="__('Auto-generated from first and last name')"
						/>
					</div>
				</template>

				<!-- Mobile Number with Country Code Selector -->
				<div>
					<label class="block text-start text-sm font-medium text-gray-700 mb-2">
						{{ __("Mobile Number") }} <span class="text-red-500">*</span>
					</label>
					<div class="flex gap-2">
						<!-- Country Code Dropdown -->
						<div class="relative" ref="dropdownRef">
							<button
								type="button"
								@click="showCountryDropdown = !showCountryDropdown"
								class="flex items-center gap-1 w-24 ps-2 pe-1 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white hover:bg-gray-50"
							>
								<img
									v-if="currentCountryCode"
									:src="`https://flagcdn.com/h24/${currentCountryCode}.png`"
									:alt="currentCountryCode"
									class="w-6 h-auto rounded-sm"
									@error="handleFlagError"
								/>
								<svg
									v-else
									class="w-4 h-4 text-gray-400"
									fill="currentColor"
									viewBox="0 0 20 20"
								>
									<path
										fill-rule="evenodd"
										d="M10 18a8 8 0 100-16 8 8 0 000 16zM4.332 8.027a6.012 6.012 0 011.912-2.706C6.512 5.73 6.974 6 7.5 6A1.5 1.5 0 019 7.5V8a2 2 0 004 0 2 2 0 011.523-1.943A5.977 5.977 0 0116 10c0 .34-.028.675-.083 1H15a2 2 0 00-2 2v2.197A5.973 5.973 0 0110 16v-2a2 2 0 00-2-2 2 2 0 01-2-2 2 2 0 00-1.668-1.973z"
										clip-rule="evenodd"
									/>
								</svg>
								<span class="flex-1 text-start">{{
									selectedCountryCode || "+"
								}}</span>
								<svg
									class="w-4 h-4 text-gray-400"
									fill="none"
									stroke="currentColor"
									viewBox="0 0 24 24"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M19 9l-7 7-7-7"
									/>
								</svg>
							</button>

							<!-- Country Search Dropdown -->
							<div
								v-if="showCountryDropdown"
								class="absolute start-0 z-50 mt-1 w-80 max-h-80 bg-white rounded-lg shadow-lg border border-gray-200 overflow-hidden"
							>
								<div class="sticky top-0 bg-white border-b border-gray-200 p-2">
									<input
										ref="countrySearchRef"
										v-model="countrySearchQuery"
										type="text"
										:placeholder="__('Search country or code...')"
										class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
										@keydown.escape="showCountryDropdown = false"
									/>
								</div>
								<div class="overflow-y-auto max-h-64">
									<button
										v-for="country in filteredCountries"
										:key="country.code"
										type="button"
										@click="selectCountry(country)"
										class="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-gray-50 transition-colors text-start"
										:class="{
											'bg-blue-50': isSelectedCountry(country),
										}"
									>
										<img
											:src="`https://flagcdn.com/h24/${country.code.toLowerCase()}.png`"
											:alt="country.name"
											class="w-6 h-auto rounded-sm shadow-sm"
											@error="(e) => (e.target.style.display = 'none')"
										/>
										<span class="flex-1 text-sm font-medium text-gray-700">{{
											country.name
										}}</span>
										<span class="text-sm text-gray-500">{{
											country.isd
										}}</span>
									</button>
									<div
										v-if="filteredCountries.length === 0"
										class="px-4 py-8 text-center text-sm text-gray-500"
									>
										{{ __("No countries found") }}
									</div>
								</div>
							</div>
						</div>

						<!-- Phone Number Input -->
						<input
							v-model="phoneNumber"
							type="tel"
							:placeholder="__('Enter phone number')"
							class="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-start"
							@input="updateMobileNumber"
							required
						/>
					</div>
				</div>

				<!-- Email -->
				<div>
					<label class="block text-start text-sm font-medium text-gray-700 mb-2">
						{{ __("Email") }}
					</label>
					<Input
						v-model="customerData.email_id"
						type="email"
						:placeholder="
							miraayaCustomerSync
								? __('Enter email address (optional)')
								: __('Enter email address')
						"
					/>
				</div>

				<!-- Customer Group -->
				<div>
					<label class="block text-start text-sm font-medium text-gray-700 mb-2">
						{{ __("Customer Group") }}
					</label>
					<select
						v-model="customerData.customer_group"
						class="w-full px-8 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
					>
						<option value="">{{ __("Select Customer Group") }}</option>
						<option v-for="group in customerGroups" :key="group" :value="group">
							{{ group }}
						</option>
					</select>
				</div>

				<!-- Territory -->
				<div>
					<label class="block text-start text-sm font-medium text-gray-700 mb-2">
						{{ __("Territory") }}
					</label>
					<select
						v-model="customerData.territory"
						class="w-full px-8 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
					>
						<option value="">{{ __("Select Territory") }}</option>
						<option
							v-for="territory in territories"
							:key="territory"
							:value="territory"
						>
							{{ territory }}
						</option>
					</select>
				</div>

				<!-- Governorate -->
				<div>
					<label class="block text-start text-sm font-medium text-gray-700 mb-2">
						{{ __("Governorate") }}
					</label>
					<select
						v-model="customerData.custom_governorate"
						class="w-full px-8 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
					>
						<option value="">{{ __("Select Governorate") }}</option>
						<option v-for="gov in governorates" :key="gov" :value="gov">
							{{ gov }}
						</option>
					</select>
				</div>

				<!-- District (filtered by selected Governorate) -->
				<div>
					<label class="block text-start text-sm font-medium text-gray-700 mb-2">
						{{ __("District") }}
					</label>
					<select
						v-model="customerData.custom_district"
						:disabled="!customerData.custom_governorate"
						class="w-full px-8 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
					>
						<option value="">
							{{
								customerData.custom_governorate
									? __("Select District")
									: __("Select a governorate first")
							}}
						</option>
						<option
							v-for="district in districts"
							:key="district.name"
							:value="district.name"
						>
							{{ district.district }}
						</option>
					</select>
				</div>
			</div>
		</template>

		<template #actions>
			<div class="flex flex-col gap-2">
				<!-- Permission Warning -->
				<div
					v-if="!hasPermission"
					class="px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg"
				>
					<div class="flex items-start gap-2">
						<svg
							class="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5"
							fill="currentColor"
							viewBox="0 0 20 20"
						>
							<path
								fill-rule="evenodd"
								d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
								clip-rule="evenodd"
							/>
						</svg>
						<div class="flex-1">
							<p class="text-sm font-medium text-amber-900">
								{{ __("Permission Required") }}
							</p>
							<p class="text-xs text-amber-700 mt-0.5">
								{{
									__(
										"You don't have permission to create customers. Contact your administrator."
									)
								}}
							</p>
						</div>
					</div>
				</div>

				<div class="flex gap-2">
					<Button
						variant="solid"
						@click="handleCreate"
						:loading="
							createCustomerResource.loading ||
							updateCustomerResource.loading ||
							checkingPermission
						"
						:disabled="!canSubmitCustomer"
					>
						{{ isEditMode ? __("Save Changes") : __("Create Customer") }}
					</Button>
					<Button variant="subtle" @click="show = false">
						{{ __("Cancel") }}
					</Button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
/**
 * CreateCustomerDialog - Quick customer creation from POS
 *
 * Features:
 * - Country code selector with flag icons and search
 * - Default mobile ISD from POS Profile country (Company.country)
 * - Auto-sets territory based on selected country
 * - Permission checking before allowing creation
 * - Lazy loads countries data when dialog opens (not on app startup)
 */

import { usePOSPermissions } from "@/composables/usePermissions";
import { shiftState } from "@/composables/useShift";
import { useToast } from "@/composables/useToast";
import { useBootstrapStore } from "@/stores/bootstrap";
import { useCountriesStore } from "@/stores/countries";
import { usePOSSettingsStore } from "@/stores/posSettings";
import { usePOSShiftStore } from "@/stores/posShift";
import { isMagentoAppInstalled } from "@/utils/magento";
import { logger } from "@/utils/logger";
import { Button, Dialog, Input, createResource } from "frappe-ui";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const log = logger.create("CreateCustomerDialog");

function defaultPosEmail(email, mobile) {
	const trimmed = (email || "").trim();
	if (trimmed) return trimmed;
	const digits = String(mobile || "").replace(/\D/g, "");
	return `pos.${digits || "customer"}@pos.miraaya`;
}


// =============================================================================
// Composables & Stores
// =============================================================================

const countriesStore = useCountriesStore();
const posSettingsStore = usePOSSettingsStore();
const shiftStore = usePOSShiftStore();
const bootstrapStore = useBootstrapStore();
const { canCreateCustomer } = usePOSPermissions();
const { showSuccess, showError } = useToast();

// =============================================================================
// Props & Emits
// =============================================================================

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
	initialName: String,
	customer: Object, // Customer object for edit mode
});

const emit = defineEmits(["update:modelValue", "customer-created", "customer-updated"]);

// =============================================================================
// State
// =============================================================================

const hasPermission = ref(true);
const checkingPermission = ref(false);
const selectedCountryCode = ref("");
const selectedCountryName = ref("");
const phoneNumber = ref("");
const showCountryDropdown = ref(false);
const countrySearchQuery = ref("");
const dropdownRef = ref(null);
const countrySearchRef = ref(null);
/** Ensures POS Profile default ISD is applied only once per dialog open */
const defaultCountryApplied = ref(false);

const customerGroups = ref([]);
const territories = ref([]);
const governorates = ref([]);
const districts = ref([]);

const customerData = ref({
	customer_name: "",
	mobile_no: "",
	email_id: "",
	customer_group: "",
	territory: "",
	custom_governorate: "",
	custom_district: "",
	custom_first_name: "",
	custom_last_name: "",
});

// =============================================================================
// Computed
// =============================================================================

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit("update:modelValue", val),
});

const isEditMode = computed(() => !!props.customer?.name);

const miraayaCustomerSync = computed(
	() =>
		Boolean(posSettingsStore.miraayaInstalled) ||
		Boolean(posSettingsStore.magentoLoyaltyAvailable) ||
		isMagentoAppInstalled()
);

const computedCustomerName = computed(() => {
	const first = (customerData.value.custom_first_name || "").trim();
	const last = (customerData.value.custom_last_name || "").trim();
	return [first, last].filter(Boolean).join(" ");
});

const hasValidCustomerName = computed(() => {
	if (miraayaCustomerSync.value) {
		return Boolean(computedCustomerName.value);
	}
	return Boolean((customerData.value.customer_name || "").trim());
});

const canSubmitCustomer = computed(
	() => hasValidCustomerName.value && Boolean(phoneNumber.value) && hasPermission.value
);

const currentCountryCode = computed(() => {
	const byName = selectedCountryName.value
		? countriesStore.findCountryByName(selectedCountryName.value)
		: null;
	if (byName?.code) return byName.code.toLowerCase();
	const country = countriesStore.countries.find((c) => c.isd === selectedCountryCode.value);
	return country?.code.toLowerCase() || "";
});

const filteredCountries = computed(() => {
	if (!countrySearchQuery.value) return countriesStore.countries;

	const query = countrySearchQuery.value.toLowerCase();
	return countriesStore.countries.filter(
		(c) =>
			c.name.toLowerCase().includes(query) ||
			c.isd.includes(query) ||
			c.code.toLowerCase().includes(query)
	);
});

// =============================================================================
// Country & Territory Methods
// =============================================================================

const handleFlagError = (e) => (e.target.style.display = "none");

const isSelectedCountry = (country) => {
	if (selectedCountryName.value) return country.name === selectedCountryName.value;
	return country.isd === selectedCountryCode.value;
};

const selectCountry = (country) => {
	selectedCountryCode.value = country.isd;
	selectedCountryName.value = country.name || "";
	showCountryDropdown.value = false;
	countrySearchQuery.value = "";
	updateMobileNumber();
	// Manual pick only — do not auto-change territory on open/default
	updateTerritoryFromCountry();
};

const updateMobileNumber = () => {
	customerData.value.mobile_no = phoneNumber.value
		? `${selectedCountryCode.value}-${phoneNumber.value}`
		: "";
};

const handleClickOutside = (event) => {
	if (dropdownRef.value && !dropdownRef.value.contains(event.target)) {
		showCountryDropdown.value = false;
		countrySearchQuery.value = "";
	}
};

/** Resolve ISD from country name, ISO code, or ISD itself. */
const resolveCountryIsd = (value) => {
	if (!value) return null;

	const byName = countriesStore.countryNameToISDMap[value];
	if (byName) return byName;

	const byCode = countriesStore.findCountryByCode(value);
	if (byCode?.isd) return byCode.isd;

	const byIsd = countriesStore.findCountryByISD(value);
	if (byIsd?.isd) return byIsd.isd;

	if (String(value).startsWith("+")) return value;

	return null;
};

/** Set selectedCountryCode from POS Profile country / country code (once). */
const setCountryFromProfileValue = (profileCountry) => {
	const isd = resolveCountryIsd(profileCountry);
	if (!isd) {
		log.warn(`Country "${profileCountry}" not found in countries list`);
		return false;
	}
	selectedCountryCode.value = isd;
	const matched = countriesStore.findCountryByName(profileCountry);
	selectedCountryName.value = matched?.name || profileCountry || "";
	log.info(`Set country code to ${isd} for ${profileCountry}`);
	return true;
};

/** POS Profile / Company country already in memory (no network). */
const resolvePosProfileCountrySync = () =>
	shiftStore.currentProfile?.country ||
	bootstrapStore.getPreloadedPOSProfile()?.country ||
	shiftState.value.company?.country ||
	null;

/** POS Profile country (Company → country), from shift/bootstrap or API. */
const resolvePosProfileCountry = async () => {
	const cached = resolvePosProfileCountrySync();
	if (cached) return cached;

	if (!props.posProfile) return null;

	try {
		const data = await posProfileResource.reload();
		return data?.country || shiftState.value.company?.country || null;
	} catch (err) {
		log.error("Error loading POS Profile country", err);
		return shiftState.value.company?.country || null;
	}
};

/**
 * Apply default mobile ISD once when opening Create Customer.
 * Uses in-memory POS Profile / Company country — never Egypt/US fallbacks.
 * Does nothing in edit mode, and never re-applies after open / user pick.
 */
const applyDefaultCountryCode = async () => {
	if (isEditMode.value || defaultCountryApplied.value || selectedCountryCode.value) {
		defaultCountryApplied.value = true;
		return;
	}

	const cachedCountry = resolvePosProfileCountrySync();
	if (countriesStore.loaded && cachedCountry && setCountryFromProfileValue(cachedCountry)) {
		defaultCountryApplied.value = true;
		return;
	}

	await countriesStore.loadCountries();

	if (selectedCountryCode.value) {
		defaultCountryApplied.value = true;
		return;
	}

	const profileCountry = await resolvePosProfileCountry();

	if (selectedCountryCode.value) {
		defaultCountryApplied.value = true;
		return;
	}

	setCountryFromProfileValue(profileCountry);
	defaultCountryApplied.value = true;
};

/** Auto-set territory based on selected country (exact or fuzzy match) */
const updateTerritoryFromCountry = () => {
	if (!territories.value.length) return;

	const country = countriesStore.countries.find((c) => c.isd === selectedCountryCode.value);
	if (!country) return;

	// Try exact match first
	if (territories.value.includes(country.name)) {
		customerData.value.territory = country.name;
		log.info(`Territory set to: ${country.name}`);
		return;
	}

	// Try fuzzy match
	const fuzzyMatch = territories.value.find(
		(t) =>
			t.toLowerCase().includes(country.name.toLowerCase()) ||
			country.name.toLowerCase().includes(t.toLowerCase())
	);

	if (fuzzyMatch) {
		customerData.value.territory = fuzzyMatch;
		log.info(`Territory set to fuzzy match: ${fuzzyMatch}`);
	}
};

// =============================================================================
// API Resources
// =============================================================================

const createCustomerResource = createResource({
	url: "pos_next.api.customers.create_customer",
	makeParams: () => {
		const params = {
			customer_name: miraayaCustomerSync.value
				? computedCustomerName.value
				: customerData.value.customer_name,
			mobile_no: customerData.value.mobile_no || "",
			email_id: miraayaCustomerSync.value
				? defaultPosEmail(customerData.value.email_id, customerData.value.mobile_no)
				: customerData.value.email_id || "",
			customer_group: customerData.value.customer_group || "",
			territory: customerData.value.territory || "",
			custom_governorate: customerData.value.custom_governorate || "",
			custom_district: customerData.value.custom_district || "",
			pos_profile: props.posProfile,
		};
		if (miraayaCustomerSync.value) {
			params.custom_first_name = customerData.value.custom_first_name || "";
			params.custom_last_name = customerData.value.custom_last_name || "";
			params.custom_is_publish = 1;
		}
		return params;
	},
	onSuccess: (data) => {
		showSuccess(__("Customer {0} created successfully", [data.customer_name]));
		emit("customer-created", data);
		show.value = false;
	},
	onError: (error) => {
		log.error("Error creating customer", error);
		showError(error.message || __("Failed to create customer"));
	},
});

const updateCustomerResource = createResource({
	url: "frappe.client.set_value",
	makeParams: () => {
		const fieldname = {
			customer_name: miraayaCustomerSync.value
				? computedCustomerName.value
				: customerData.value.customer_name,
			customer_group: customerData.value.customer_group || "",
			territory: customerData.value.territory || "",
			mobile_no: customerData.value.mobile_no || "",
			email_id: customerData.value.email_id || "",
			custom_governorate: customerData.value.custom_governorate || "",
			custom_district: customerData.value.custom_district || "",
		};
		if (miraayaCustomerSync.value) {
			fieldname.custom_first_name = customerData.value.custom_first_name || "";
			fieldname.custom_last_name = customerData.value.custom_last_name || "";
		}
		return {
			doctype: "Customer",
			name: props.customer?.name,
			fieldname,
		};
	},
	onSuccess: (data) => {
		showSuccess(__("Customer {0} updated successfully", [data.customer_name]));
		emit("customer-updated", data);
		show.value = false;
	},
	onError: (error) => {
		log.error("Error updating customer", error);
		showError(error.message || __("Failed to update customer"));
	},
});

const sellingSettingsResource = createResource({
	url: "frappe.client.get_value",
	makeParams: () => ({
		doctype: "Selling Settings",
		fieldname: ["customer_group", "territory"],
	}),
	auto: false,
	onError: (err) => log.error("Error loading Selling Settings", err),
});

function pickDefault(settingsValue, list, fallbackFn = null) {
	if (settingsValue && list.includes(settingsValue)) return settingsValue;
	if (fallbackFn) return fallbackFn(list) || list[0] || "";
	return list[0] || "";
}

/** Helper to create list fetch resources */
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
	});

const customerGroupsResource = createListResource("Customer Group", (names) => {
	customerGroups.value = names;
	if (!customerData.value.customer_group && names.length > 0) {
		const settingsDefault = sellingSettingsResource.data?.customer_group;
		customerData.value.customer_group = pickDefault(settingsDefault, names);
	}
});

const territoriesResource = createListResource("Territory", (names) => {
	territories.value = names;
	if (!customerData.value.territory && names.length > 0) {
		const settingsDefault = sellingSettingsResource.data?.territory;
		customerData.value.territory = pickDefault(settingsDefault, names, (list) =>
			list.find((n) => n === "All Territories")
		);
	}
});

const governoratesResource = createListResource("Governorate", (names) => {
	governorates.value = names;
});

const customerLocationResource = createResource({
	url: "frappe.client.get_value",
	makeParams: () => ({
		doctype: "Customer",
		filters: { name: props.customer?.name },
		fieldname: ["custom_governorate", "custom_district"],
	}),
	auto: false,
	onSuccess: (data) => {
		customerData.value.custom_governorate = data?.custom_governorate || "";
		customerData.value.custom_district = data?.custom_district || "";
	},
	onError: (err) => log.error("Error loading customer location", err),
});

const districtsResource = createResource({
	url: "frappe.client.get_list",
	makeParams: () => ({
		doctype: "District",
		fields: ["name", "district"],
		filters: { governorate: customerData.value.custom_governorate },
		limit_page_length: 0,
		order_by: "district asc",
	}),
	auto: false,
	onSuccess: (data) => {
		districts.value = data || [];
		// Drop the selected district if it no longer belongs to the governorate
		if (
			customerData.value.custom_district &&
			!districts.value.some((d) => d.name === customerData.value.custom_district)
		) {
			customerData.value.custom_district = "";
		}
	},
	onError: (err) => log.error("Error loading Districts", err),
});

const posProfileResource = createResource({
	url: "frappe.client.get_value",
	makeParams: () => ({
		doctype: "POS Profile",
		filters: { name: props.posProfile },
		fieldname: ["country"],
	}),
	auto: false,
	onError: (err) => log.error("Error loading POS Profile", err),
});

// =============================================================================
// Dialog Lifecycle
// =============================================================================

const loadDialogData = async () => {
	// Default ISD first so the dialog never paints Egypt/+20 then swaps
	const countryPromise = applyDefaultCountryCode();

	await sellingSettingsResource.reload();

	if (!isEditMode.value) {
		customerData.value.customer_group = "";
		customerData.value.territory = "";
	}

	// Load form options
	await Promise.all([
		countryPromise,
		territoriesResource.reload(),
		customerGroupsResource.reload(),
		governoratesResource.reload(),
	]);
	if (isEditMode.value && props.customer?.name) {
		await customerLocationResource.reload();
	}
	if (customerData.value.custom_governorate) {
		await districtsResource.reload();
	}
	checkPermissions();
};

const checkPermissions = async () => {
	checkingPermission.value = true;
	try {
		hasPermission.value = await canCreateCustomer();
	} catch (err) {
		log.error("Permission check failed", err);
		hasPermission.value = false;
	} finally {
		checkingPermission.value = false;
	}
};

const handleCreate = async () => {
	if (miraayaCustomerSync.value) {
		if (!customerData.value.custom_first_name?.trim()) {
			return showError(__("First Name is required"));
		}
		if (!customerData.value.custom_last_name?.trim()) {
			return showError(__("Last Name is required"));
		}
	} else if (!customerData.value.customer_name) {
		return showError(__("Customer Name is required"));
	}
	if (!phoneNumber.value) {
		return showError(__("Mobile Number is required"));
	}
	if (isEditMode.value) {
		await updateCustomerResource.submit();
	} else {
		await createCustomerResource.submit();
	}
};

const resetForm = () => {
	const settings = sellingSettingsResource.data || {};
	Object.assign(customerData.value, {
		customer_name: "",
		mobile_no: "",
		email_id: "",
		customer_group: pickDefault(settings.customer_group, customerGroups.value),
		territory: pickDefault(settings.territory, territories.value, (list) =>
			list.find((n) => n === "All Territories")
		),
		custom_governorate: "",
		custom_district: "",
		custom_first_name: "",
		custom_last_name: "",
	});
	districts.value = [];
	selectedCountryCode.value = "";
	selectedCountryName.value = "";
	phoneNumber.value = "";
	defaultCountryApplied.value = false;
};

// =============================================================================
// Watchers
// =============================================================================

watch(
	() => props.initialName,
	(name) => {
		if (!name) return;
		if (miraayaCustomerSync.value) {
			if (!customerData.value.custom_first_name) {
				customerData.value.custom_first_name = name.trim();
			}
		} else {
			customerData.value.customer_name = name;
		}
	}
);

// Pre-fill form when customer prop changes (edit mode)
watch(
	() => props.customer,
	(customer) => {
		if (customer?.name) {
			customerData.value.customer_name = customer.customer_name || "";
			customerData.value.email_id = customer.email_id || "";
			customerData.value.customer_group =
				customer.customer_group || customerGroups.value[0] || "";
			customerData.value.territory =
				customer.territory ||
				territories.value.find((n) => n === "All Territories") ||
				territories.value[0] ||
				"";

			customerData.value.custom_governorate = customer.custom_governorate || "";
			customerData.value.custom_district = customer.custom_district || "";
			customerData.value.custom_first_name = customer.custom_first_name || "";
			customerData.value.custom_last_name = customer.custom_last_name || "";
			if (
				miraayaCustomerSync.value &&
				!customerData.value.custom_first_name &&
				(customer.customer_name || "").trim()
			) {
				const parts = customer.customer_name.trim().split(/\s+/, 2);
				customerData.value.custom_first_name = parts[0] || "";
				customerData.value.custom_last_name = parts[1] || parts[0] || "";
			}
			// Handle mobile_no with country code
			if (customer.mobile_no) {
				customerData.value.mobile_no = customer.mobile_no;
				if (customer.mobile_no.includes("-")) {
					const [code, ...rest] = customer.mobile_no.split("-");
					selectedCountryCode.value = code;
					selectedCountryName.value =
						countriesStore.findCountryByISD(code)?.name || "";
					phoneNumber.value = rest.join("-");
				} else {
					phoneNumber.value = customer.mobile_no;
				}
			}
		}
	},
	{ immediate: true }
);

watch(
	() => customerData.value.mobile_no,
	(value) => {
		if (!isEditMode.value) return;
		if (value?.includes("-")) {
			const [code, ...rest] = value.split("-");
			selectedCountryCode.value = code;
			selectedCountryName.value = countriesStore.findCountryByISD(code)?.name || "";
			phoneNumber.value = rest.join("-");
		}
	}
);

watch(selectedCountryCode, async (newVal, oldVal) => {
	if (!oldVal) return;
	await nextTick();
	updateTerritoryFromCountry();
});

watch(
	() => customerData.value.custom_governorate,
	(governorate) => {
		if (governorate) {
			districtsResource.reload();
		} else {
			districts.value = [];
			customerData.value.custom_district = "";
		}
	}
);

watch(showCountryDropdown, async (isOpen) => {
	if (isOpen) {
		await nextTick();
		countrySearchRef.value?.focus();
	}
});

watch(
	() => props.modelValue,
	async (isOpen) => {
		if (!isOpen) {
			resetForm();
			return;
		}
		await loadDialogData();
	}
);

// =============================================================================
// Lifecycle Hooks
// =============================================================================

onMounted(() => {
	document.addEventListener("click", handleClickOutside);
	// Preload country ISD map so Create Customer opens on the profile country, not a flash
	countriesStore.loadCountries();
});

onBeforeUnmount(() => {
	document.removeEventListener("click", handleClickOutside);
});
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
