<template>
	<Dialog
		v-model="show"
		:key="dialogKey"
		:options="dialogOptions"
	>
		<template #body-content>
			<div
				class="-mx-4 overflow-y-auto overscroll-contain px-4 pb-1 sm:-mx-6 sm:px-6"
				:style="{ maxHeight: 'max(14rem, calc(100dvh - 17.5rem))' }"
				data-testid="customer-dialog-body"
			>
				<!-- Post-create step: offer email verification for the new customer -->
				<div v-if="createdCustomer" class="flex flex-col gap-4" data-testid="created-verify-step">
					<CustomerIdentityStrip
						tone="success"
						:name="createdCustomer.customer_name"
						:phone="formatPhone(createdCustomer.mobile_no)"
						:id="createdCustomer.name !== createdCustomer.customer_name ? createdCustomer.name : ''"
						:status="Number(createdCustomer.custom_email_verified) ? 'verified' : 'unverified'"
					/>
					<p class="text-pos-md text-pos-ink">
						{{ __("Customer {0} created successfully", [createdCustomer.customer_name]) }}
					</p>
					<EmailVerificationPanel
						:customer="createdCustomer.name"
						:email="customerData.email_id"
						:saved-email="createdCustomer.email_id || ''"
						:verified="Boolean(Number(createdCustomer.custom_email_verified))"
						:verified-email="createdCustomer.custom_verified_email || ''"
						:pos-profile="posProfile"
						@verified="handleEmailVerified"
						@lock-change="(v) => (emailVerificationLocked = v)"
					/>
				</div>

				<div v-else class="flex flex-col gap-5">
					<!-- Duplicate: the entered email or phone already belongs to another customer -->
					<div
						v-if="existingDuplicate"
						class="flex flex-col gap-3 rounded-xl border border-amber-300 bg-amber-50 p-3 sm:p-4"
						data-testid="existing-customer-warning"
						role="alert"
					>
						<p class="text-pos-md font-medium text-amber-900">
							{{ existingDuplicate.message }}
						</p>
						<CustomerIdentityStrip
							tone="caution"
							:name="existingDuplicate.existing_customer.customer_name"
							:phone="existingDuplicate.existing_customer.mobile_no || ''"
							:id="existingDuplicate.existing_customer.name"
						/>
						<p
							v-if="existingDuplicate.existing_customer.email_id"
							class="text-pos-sm text-amber-900"
							dir="ltr"
						>
							{{ existingDuplicate.existing_customer.email_id }}
						</p>
					</div>

					<!-- Who the cashier is attaching to the invoice, updated as they type -->
					<CustomerIdentityStrip
						v-else
						:name="displayName"
						:placeholder="__('New customer')"
						:phone="previewPhone"
						:id="isEditMode && editingCustomerName !== displayName ? editingCustomerName : ''"
						:status="identityStatus"
					/>

					<div class="grid grid-cols-1 gap-5 lg:grid-cols-5 lg:gap-6">
						<!-- Essentials -->
						<div class="flex flex-col gap-4 lg:col-span-3">
							<div v-if="!requiresSplitCustomerName">
								<label :for="ids.name" class="mb-1.5 block text-start text-pos-sm font-medium text-pos-ink">
									{{ __("Customer Name") }}
									<span class="text-pos-danger" aria-hidden="true">*</span>
									<span class="sr-only">({{ __("Required") }})</span>
								</label>
								<input
									:id="ids.name"
									v-model="customerData.customer_name"
									type="text"
									autocomplete="off"
									:placeholder="__('Enter customer name')"
									:class="controlClass(fieldErrors.customer_name)"
									:aria-invalid="Boolean(fieldErrors.customer_name)"
									:aria-describedby="fieldErrors.customer_name ? `${ids.name}-error` : undefined"
									required
								/>
								<div aria-live="polite">
									<p v-if="fieldErrors.customer_name" :id="`${ids.name}-error`" class="mt-1 text-start text-xs text-pos-danger" data-testid="error-customer-name">
										{{ fieldErrors.customer_name }}
									</p>
								</div>
							</div>

							<div v-else class="grid grid-cols-1 gap-4 sm:grid-cols-2">
								<div>
									<label :for="ids.first" class="mb-1.5 block text-start text-pos-sm font-medium text-pos-ink">
										{{ __("First Name") }}
										<span class="text-pos-danger" aria-hidden="true">*</span>
										<span class="sr-only">({{ __("Required") }})</span>
									</label>
									<input
										:id="ids.first"
										v-model="customerData.custom_first_name"
										type="text"
										autocomplete="off"
										:placeholder="__('First name')"
										:class="controlClass(fieldErrors.custom_first_name)"
										:aria-invalid="Boolean(fieldErrors.custom_first_name)"
										:aria-describedby="fieldErrors.custom_first_name ? `${ids.first}-error` : undefined"
										data-testid="customer-first-name"
										required
									/>
									<div aria-live="polite">
										<p v-if="fieldErrors.custom_first_name" :id="`${ids.first}-error`" class="mt-1 text-start text-xs text-pos-danger" data-testid="error-first-name">
											{{ fieldErrors.custom_first_name }}
										</p>
									</div>
								</div>
								<div>
									<label :for="ids.last" class="mb-1.5 block text-start text-pos-sm font-medium text-pos-ink">
										{{ __("Last Name") }}
										<span class="text-pos-danger" aria-hidden="true">*</span>
										<span class="sr-only">({{ __("Required") }})</span>
									</label>
									<input
										:id="ids.last"
										v-model="customerData.custom_last_name"
										type="text"
										autocomplete="off"
										:placeholder="__('Last name')"
										:class="controlClass(fieldErrors.custom_last_name)"
										:aria-invalid="Boolean(fieldErrors.custom_last_name)"
										:aria-describedby="fieldErrors.custom_last_name ? `${ids.last}-error` : undefined"
										data-testid="customer-last-name"
										required
									/>
									<div aria-live="polite">
										<p v-if="fieldErrors.custom_last_name" :id="`${ids.last}-error`" class="mt-1 text-start text-xs text-pos-danger" data-testid="error-last-name">
											{{ fieldErrors.custom_last_name }}
										</p>
									</div>
								</div>
							</div>

							<!-- Mobile: country code + number, always laid out left to right -->
							<div ref="dropdownRef" @keydown.escape.capture="onPickerEscape">
								<label :for="ids.phone" class="mb-1.5 block text-start text-pos-sm font-medium text-pos-ink">
									{{ __("Mobile Number") }}
									<span class="text-pos-danger" aria-hidden="true">*</span>
									<span class="sr-only">({{ __("Required") }})</span>
								</label>
								<div class="flex gap-2" dir="ltr">
									<button
										ref="countryButtonRef"
										type="button"
										class="flex min-h-target w-[7.5rem] flex-shrink-0 items-center gap-2 rounded-lg border bg-white ps-2.5 pe-2 text-pos-md text-pos-ink hover:bg-gray-50 focus:border-pos-action focus:outline-none focus:ring-1 focus:ring-pos-action"
										:class="[
											fieldErrors.country ? 'border-pos-danger' : 'border-gray-300',
											showCountryDropdown ? 'border-pos-action ring-1 ring-pos-action' : '',
										]"
										:aria-label="__('Country code')"
										:aria-expanded="showCountryDropdown"
										:aria-invalid="Boolean(fieldErrors.country)"
										:aria-describedby="fieldErrors.country ? `${ids.phone}-error` : undefined"
										aria-haspopup="listbox"
										data-testid="country-code-button"
										@click="toggleCountryDropdown"
									>
										<img
											v-if="currentCountryCode && !flagFailed"
											:src="`https://flagcdn.com/h24/${currentCountryCode}.png`"
											alt=""
											class="h-4 w-6 flex-shrink-0 rounded-sm object-cover ring-1 ring-black/5"
											@error="handleFlagError"
										/>
										<span
											v-else
											class="flex h-4 w-6 flex-shrink-0 items-center justify-center rounded-sm bg-pos-panel text-[10px] font-semibold uppercase text-pos-muted"
											aria-hidden="true"
										>{{ currentCountryCode }}</span>
										<span class="flex-1 text-start font-medium tabular-nums">{{ selectedCountryCode || "+" }}</span>
										<svg
											class="h-4 w-4 flex-shrink-0 text-pos-muted transition-transform"
											:class="{ 'rotate-180': showCountryDropdown }"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
											aria-hidden="true"
										>
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
										</svg>
									</button>
									<input
										:id="ids.phone"
										v-model="phoneNumber"
										type="tel"
										inputmode="tel"
										autocomplete="off"
										dir="ltr"
										:placeholder="__('Enter phone number')"
										:class="[controlClass(fieldErrors.mobile), 'min-w-0 flex-1 tabular-nums rtl:text-right']"
										:aria-invalid="Boolean(fieldErrors.mobile)"
										:aria-describedby="fieldErrors.mobile || fieldErrors.country ? `${ids.phone}-error` : undefined"
										@input="updateMobileNumber"
										required
									/>
								</div>
								<div aria-live="polite">
									<p
										v-if="fieldErrors.mobile || fieldErrors.country"
										:id="`${ids.phone}-error`"
										class="mt-1 text-start text-xs text-pos-danger"
										data-testid="error-mobile"
									>
										{{ fieldErrors.country || fieldErrors.mobile }}
									</p>
								</div>

								<!-- Country picker: opens in place under the number (never clipped by the scrolling body) -->
								<div
									v-if="showCountryDropdown"
									class="mt-2 overflow-hidden rounded-xl border border-gray-300 bg-white shadow-sm"
									data-testid="country-picker"
								>
									<div class="relative border-b border-pos-line p-2">
										<svg
											class="pointer-events-none absolute start-5 top-1/2 h-4 w-4 -translate-y-1/2 text-pos-muted"
											fill="none"
											stroke="currentColor"
											stroke-width="2"
											viewBox="0 0 24 24"
											aria-hidden="true"
										>
											<circle cx="11" cy="11" r="7" />
											<path d="M20 20l-3.5-3.5" stroke-linecap="round" />
										</svg>
										<input
											ref="countrySearchRef"
											v-model="countrySearchQuery"
											type="search"
											autocomplete="off"
											:placeholder="__('Search country or code...')"
											:aria-label="__('Search country or code...')"
											class="block min-h-target w-full rounded-lg border border-gray-300 bg-white pe-3 ps-9 text-pos-md text-pos-ink focus:border-pos-action focus:outline-none focus:ring-1 focus:ring-pos-action"
											@keydown.down.prevent="moveCountryHighlight(1)"
											@keydown.up.prevent="moveCountryHighlight(-1)"
											@keydown.enter.prevent="selectHighlightedCountry"
										/>
									</div>
									<ul
										ref="countryListRef"
										class="max-h-64 overflow-y-auto overscroll-contain py-1"
										role="listbox"
										:aria-label="__('Country code')"
									>
										<li
											v-for="(country, index) in filteredCountries"
											:key="country.code"
											role="option"
											:aria-selected="selectedCountryCode === country.isd"
											:data-index="index"
											class="flex min-h-target cursor-pointer items-center gap-3 px-3 text-start"
											:class="[
												index === countryHighlight ? 'bg-pos-panel' : '',
												selectedCountryCode === country.isd ? 'text-pos-action' : 'text-pos-ink',
											]"
											@mouseenter="countryHighlight = index"
											@click="selectCountry(country)"
										>
											<img
												:src="`https://flagcdn.com/h24/${country.code.toLowerCase()}.png`"
												alt=""
												loading="lazy"
												class="h-4 w-6 flex-shrink-0 rounded-sm object-cover ring-1 ring-black/5"
												@error="(e) => (e.target.style.visibility = 'hidden')"
											/>
											<span class="min-w-0 flex-1 truncate text-pos-md" dir="auto">{{ country.name }}</span>
											<span class="flex-shrink-0 text-pos-sm tabular-nums text-pos-muted" dir="ltr">{{ country.isd }}</span>
											<svg
												class="h-4 w-4 flex-shrink-0"
												:class="selectedCountryCode === country.isd ? 'visible' : 'invisible'"
												fill="none"
												stroke="currentColor"
												stroke-width="2.5"
												viewBox="0 0 24 24"
												aria-hidden="true"
											>
												<path d="M5 12l5 5L20 7" stroke-linecap="round" stroke-linejoin="round" />
											</svg>
										</li>
										<li
											v-if="filteredCountries.length === 0"
											class="px-4 py-6 text-center text-pos-sm text-pos-muted"
										>
											{{ __("No countries found") }}
										</li>
									</ul>
								</div>
							</div>

							<!-- Email (optional) with its verification panel docked underneath -->
							<div>
								<div class="mb-1.5 flex items-baseline justify-between gap-2">
									<label :for="ids.email" class="block text-start text-pos-sm font-medium text-pos-ink">
										{{ __("Email") }}
									</label>
									<span class="text-xs text-pos-muted">{{ __("Optional") }}</span>
								</div>
								<input
									:id="ids.email"
									v-model="customerData.email_id"
									type="email"
									inputmode="email"
									autocomplete="off"
									dir="ltr"
									:placeholder="__('Enter email address (optional)')"
									:class="[controlClass(false), 'rtl:text-right']"
									:disabled="emailVerificationLocked"
								/>
								<EmailVerificationPanel
									v-if="showEmailVerification"
									ref="verificationPanel"
									class="mt-2"
									:customer="verificationCustomerName"
									:email="customerData.email_id"
									:saved-email="verificationSavedEmail"
									:verified="verificationVerified"
									:verified-email="verificationVerifiedEmail"
									:pos-profile="posProfile"
									@verified="handleEmailVerified"
									@save-and-send="handleSaveAndSend"
									@lock-change="(v) => (emailVerificationLocked = v)"
								/>
							</div>
						</div>

						<!-- Details: usually left at their defaults -->
						<section
							class="flex flex-col gap-4 rounded-xl bg-pos-panel p-4 lg:col-span-2"
							:aria-labelledby="ids.details"
						>
							<h3 :id="ids.details" class="text-start text-pos-sm font-semibold text-pos-ink">
								{{ __("Details") }}
							</h3>
							<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-1">
								<div>
									<label :for="ids.group" class="mb-1.5 block text-start text-pos-sm font-medium text-pos-ink">
										{{ __("Customer Group") }}
									</label>
									<div class="relative">
										<select :id="ids.group" v-model="customerData.customer_group" :class="selectClass">
											<option value="">{{ __("Select Customer Group") }}</option>
											<option v-for="group in withCurrent(customerGroups, customerData.customer_group)" :key="group" :value="group">
												{{ group }}
											</option>
										</select>
										<svg class="pointer-events-none absolute end-3 top-1/2 h-4 w-4 -translate-y-1/2 text-pos-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
										</svg>
									</div>
								</div>

								<div>
									<label :for="ids.territory" class="mb-1.5 block text-start text-pos-sm font-medium text-pos-ink">
										{{ __("Territory") }}
									</label>
									<div class="relative">
										<select :id="ids.territory" v-model="customerData.territory" :class="selectClass">
											<option value="">{{ __("Select Territory") }}</option>
											<option v-for="territory in withCurrent(territories, customerData.territory)" :key="territory" :value="territory">
												{{ territory }}
											</option>
										</select>
										<svg class="pointer-events-none absolute end-3 top-1/2 h-4 w-4 -translate-y-1/2 text-pos-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
										</svg>
									</div>
								</div>

								<div>
									<label :for="ids.governorate" class="mb-1.5 block text-start text-pos-sm font-medium text-pos-ink">
										{{ __("Governorate") }}
									</label>
									<div class="relative">
										<select :id="ids.governorate" v-model="customerData.custom_governorate" :class="selectClass">
											<option value="">{{ __("Select Governorate") }}</option>
											<option v-for="gov in governorates" :key="gov" :value="gov">
												{{ gov }}
											</option>
										</select>
										<svg class="pointer-events-none absolute end-3 top-1/2 h-4 w-4 -translate-y-1/2 text-pos-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
										</svg>
									</div>
								</div>

								<!-- District (filtered by selected Governorate) -->
								<div>
									<label :for="ids.district" class="mb-1.5 block text-start text-pos-sm font-medium text-pos-ink">
										{{ __("District") }}
									</label>
									<div class="relative">
										<select
											:id="ids.district"
											v-model="customerData.custom_district"
											:disabled="!customerData.custom_governorate"
											:class="selectClass"
										>
											<option value="">
												{{
													customerData.custom_governorate
														? __("Select District")
														: __("Select a governorate first")
												}}
											</option>
											<option v-for="district in districts" :key="district.name" :value="district.name">
												{{ district.district }}
											</option>
										</select>
										<svg class="pointer-events-none absolute end-3 top-1/2 h-4 w-4 -translate-y-1/2 text-pos-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
										</svg>
									</div>
								</div>
							</div>
						</section>
					</div>
				</div>
			</div>
		</template>

		<template #actions>
			<div class="-mx-4 -mt-4 flex flex-col gap-3 border-t border-pos-line px-4 pt-4 sm:-mx-6 sm:px-6">
				<!-- Permission Warning -->
				<div
					v-if="!hasPermission"
					class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2"
					role="alert"
				>
					<div class="flex items-start gap-2">
						<svg
							class="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-600"
							fill="currentColor"
							viewBox="0 0 20 20"
							aria-hidden="true"
						>
							<path
								fill-rule="evenodd"
								d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
								clip-rule="evenodd"
							/>
						</svg>
						<div class="flex-1">
							<p class="text-pos-sm font-medium text-amber-900">
								{{ __("Permission Required") }}
							</p>
							<p class="mt-0.5 text-xs text-amber-700">
								{{
									__(
										"You don't have permission to create customers. Contact your administrator."
									)
								}}
							</p>
						</div>
					</div>
				</div>

				<div class="flex items-center justify-end gap-2">
					<template v-if="createdCustomer">
						<button type="button" :class="primaryButtonClass" @click="finishCreated">
							{{ __("Done") }}
						</button>
					</template>
					<template v-else-if="existingDuplicate">
						<button type="button" :class="secondaryButtonClass" @click="clearExistingDuplicate">
							{{ __("Back") }}
						</button>
						<button type="button" :class="primaryButtonClass" @click="selectExistingCustomer">
							{{ __("Select this customer") }}
						</button>
					</template>
					<template v-else>
						<button type="button" :class="secondaryButtonClass" @click="show = false">
							{{ __("Cancel") }}
						</button>
						<button
							type="button"
							:class="primaryButtonClass"
							:disabled="!hasPermission || submitting"
							:aria-busy="submitting"
							data-testid="customer-submit"
							@click="handleCreate"
						>
							<span
								v-if="submitting"
								class="me-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
								aria-hidden="true"
							/>{{ isEditMode ? __("Save Changes") : __("Create Customer") }}
						</button>
					</template>
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
import { useToast } from "@/composables/useToast";
import CustomerIdentityStrip from "@/components/sale/CustomerIdentityStrip.vue";
import EmailVerificationPanel from "@/components/sale/EmailVerificationPanel.vue";
import { useBootstrapStore } from "@/stores/bootstrap";
import { useCountriesStore } from "@/stores/countries";
import { usePOSSettingsStore } from "@/stores/posSettings";
import { usePOSShiftStore } from "@/stores/posShift";
import { useCustomerSearchStore } from "@/stores/customerSearch";
import { isOffline } from "@/utils/offline/offlineState";
import {
	canOfferEmailVerification,
	fetchFnfMembership,
	fetchVerificationStatus,
} from "@/utils/customerVerification";
import { logger } from "@/utils/logger";
import { Dialog, createResource } from "frappe-ui";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from "vue";

const log = logger.create("CreateCustomerDialog");

// =============================================================================
// Composables & Stores
// =============================================================================

const countriesStore = useCountriesStore();
const posSettingsStore = usePOSSettingsStore();
const shiftStore = usePOSShiftStore();
const bootstrapStore = useBootstrapStore();
const customerSearchStore = useCustomerSearchStore();
const { canCreateCustomer } = usePOSPermissions();
const { showSuccess, showError, handleError } = useToast();

// =============================================================================
// Props & Emits
// =============================================================================

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
	initialName: String,
	customer: Object, // Customer object for edit mode
});

const emit = defineEmits([
	"update:modelValue",
	"customer-created",
	"customer-updated",
	"customer-verified",
]);

// =============================================================================
// State
// =============================================================================

const hasPermission = ref(true);
const checkingPermission = ref(false);
const selectedCountryCode = ref("");
const phoneNumber = ref("");
const showCountryDropdown = ref(false);
const countrySearchQuery = ref("");
const dropdownRef = ref(null);
const countrySearchRef = ref(null);
/** Ensures POS Profile default ISD is applied only once per dialog open */
const defaultCountryApplied = ref(false);

/** Email OTP verification (flag: POS Settings > Enable Customer Email Verification) */
const emailVerificationLocked = ref(false);
/** Customer just created in this dialog, kept open to offer "Verify email" */
const createdCustomer = ref(null);
const existingDuplicate = ref(null);
const verifiedOverride = ref(null);
/** Fresh server status fetched when the dialog opens in edit mode (cached objects can be stale) */
const freshVerification = ref(null);

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

const editingCustomerName = computed(() => {
	const customer = props.customer;
	if (!customer) return "";
	if (typeof customer === "string") return customer;
	return customer.name || "";
});
const isEditMode = computed(() => !!editingCustomerName.value);
const dialogKey = computed(() =>
	isEditMode.value ? `edit-${editingCustomerName.value}` : "create"
);
const dialogOptions = computed(() => ({
	title: isEditMode.value ? __("Edit Customer") : __("Create New Customer"),
	size: "4xl",
}));

// =============================================================================
// Presentation
// =============================================================================

/** Unique ids for label/field/error wiring (the dialog is mounted in two places) */
const uid = useId();
const ids = Object.fromEntries(
	["name", "first", "last", "phone", "email", "details", "group", "territory", "governorate", "district"].map(
		(key) => [key, `ccd-${uid}-${key}`]
	)
);

const CONTROL_BASE =
	"block w-full min-h-target rounded-lg border bg-white px-3 text-pos-md text-pos-ink placeholder:text-gray-400 " +
	"focus:border-pos-action focus:outline-none focus:ring-1 focus:ring-pos-action " +
	"disabled:cursor-not-allowed disabled:bg-pos-panel disabled:text-pos-muted";
const controlClass = (hasError) =>
	`${CONTROL_BASE} ${hasError
		? "border-pos-danger ring-1 ring-pos-danger focus:border-pos-danger focus:ring-pos-danger"
		: "border-gray-300"}`;
// Room for the chevron on the end side, so placeholders are not clipped in either direction
const selectClass = `${CONTROL_BASE} border-gray-300 appearance-none bg-none truncate pe-9`;
const BUTTON_BASE =
	"inline-flex min-h-target items-center justify-center rounded-lg px-4 text-pos-md font-semibold " +
	"focus:outline-none focus-visible:ring-2 focus-visible:ring-pos-action focus-visible:ring-offset-2 " +
	"disabled:cursor-not-allowed disabled:opacity-50";
const primaryButtonClass = `${BUTTON_BASE} flex-1 sm:flex-none sm:min-w-[10rem] bg-pos-action text-white hover:bg-pos-action-hover`;
const secondaryButtonClass = `${BUTTON_BASE} border border-gray-300 bg-white text-pos-ink hover:bg-gray-50`;

/** Keep a stored value visible even when it is not in the selectable list */
const withCurrent = (list, current) => (current && !list.includes(current) ? [current, ...list] : list);

/** Inline validation messages, keyed by field; shown under the field */
const fieldErrors = ref({});

// An email on the site's placeholder domain (POS Settings) is not a real address.
// Blank setting: nothing is a placeholder.
const hasRealEmail = (email) => {
	const e = (email || "").trim().toLowerCase();
	if (!e || !e.includes("@")) return false;
	const domain = (posSettingsStore.placeholderEmailDomain || "").trim().toLowerCase().replace(/^@/, "");
	return !domain || e.split("@").pop() !== domain;
};

// F&F members need a verified email for Friends & Family, so the panel is
// offered to them even when the general POS verification switch is off.
const fnfMember = ref(false);

// Edit mode only (customer exists); create mode uses the post-create step.
const showEmailVerification = computed(
	() =>
		isEditMode.value &&
		canOfferEmailVerification({
			switchEnabled: posSettingsStore.customerEmailVerificationEnabled,
			fnfMember: fnfMember.value,
		}) &&
		hasRealEmail(savedEmailOverride.value ?? (props.customer?.email_id || customerData.value.email_id))
);
const verificationCustomerName = computed(() => editingCustomerName.value);
const verificationPanel = ref(null);
/** Email saved via "Save email & send code" (props.customer is stale until the parent refreshes) */
const savedEmailOverride = ref(null);
const saveAndSendPending = ref(false);
const verificationSavedEmail = computed(
	() => savedEmailOverride.value ?? (props.customer?.email_id || "")
);
const currentVerification = computed(
	() => verifiedOverride.value || freshVerification.value || props.customer || {}
);
const verificationVerified = computed(() =>
	Boolean(Number(currentVerification.value.custom_email_verified))
);
const verificationVerifiedEmail = computed(() => currentVerification.value.custom_verified_email || "");

const requiresSplitCustomerName = computed(() => Boolean(posSettingsStore.requireSplitName));

const computedCustomerName = computed(() => {
	const first = (customerData.value.custom_first_name || "").trim();
	const last = (customerData.value.custom_last_name || "").trim();
	return [first, last].filter(Boolean).join(" ");
});


const submitting = computed(
	() =>
		Boolean(createCustomerResource.loading) ||
		Boolean(updateCustomerResource.loading) ||
		checkingPermission.value
);

/** Name as it will appear on the cart */
const displayName = computed(() =>
	requiresSplitCustomerName.value
		? computedCustomerName.value
		: (customerData.value.customer_name || "").trim()
);

/** "+20 1000000006" from a stored "+20-1000000006" */
const formatPhone = (mobile) => (mobile || "").replace(/^(\+\d+)-/, "$1 ");

const previewPhone = computed(() =>
	phoneNumber.value ? [selectedCountryCode.value, phoneNumber.value].filter(Boolean).join(" ") : ""
);

const identityStatus = computed(() => {
	if (!isEditMode.value) return "";
	if (verificationVerified.value) return "verified";
	return showEmailVerification.value ? "unverified" : "";
});

const currentCountryCode = computed(() => {
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

const flagFailed = ref(false);
const handleFlagError = () => (flagFailed.value = true);
watch(selectedCountryCode, () => (flagFailed.value = false));

const countryButtonRef = ref(null);
const countryListRef = ref(null);
const countryHighlight = ref(-1);

const closeCountryDropdown = (returnFocus = false) => {
	showCountryDropdown.value = false;
	countrySearchQuery.value = "";
	if (returnFocus) nextTick(() => countryButtonRef.value?.focus());
};

/**
 * Escape inside the open picker closes only the picker. frappe-ui's Dialog closes on an
 * Escape that reaches window (Reka ignores preventDefault there), so the event stops here.
 */
const onPickerEscape = (event) => {
	if (!showCountryDropdown.value) return;
	event.preventDefault();
	event.stopPropagation();
	closeCountryDropdown(true);
};

const toggleCountryDropdown = () => {
	if (showCountryDropdown.value) return closeCountryDropdown();
	showCountryDropdown.value = true;
};

const scrollHighlightIntoView = () =>
	nextTick(() => {
		countryListRef.value
			?.querySelector(`[data-index="${countryHighlight.value}"]`)
			?.scrollIntoView?.({ block: "center" });
	});

const moveCountryHighlight = (step) => {
	const count = filteredCountries.value.length;
	if (!count) return;
	countryHighlight.value = (countryHighlight.value + step + count) % count;
	scrollHighlightIntoView();
};

const selectHighlightedCountry = () => {
	const list = filteredCountries.value;
	const country = list[countryHighlight.value] || (list.length === 1 ? list[0] : null);
	if (country) selectCountry(country);
};

const selectCountry = (country) => {
	selectedCountryCode.value = country.isd;
	closeCountryDropdown(true);
	updateMobileNumber();
	// Manual pick only — do not auto-change territory on open/default
	updateTerritoryFromCountry();
};

const DEFAULT_MOBILE_ISD = "+20";

const updateMobileNumber = () => {
	if (!phoneNumber.value) {
		customerData.value.mobile_no = "";
		return;
	}
	// Never persist a leading "-" when ISD is still unresolved
	customerData.value.mobile_no = selectedCountryCode.value
		? `${selectedCountryCode.value}-${phoneNumber.value}`
		: phoneNumber.value;
};

/** Split a full customer name into first + remaining last-name parts. */
const splitCustomerName = (fullName) => {
	const parts = (fullName || "").trim().split(/\s+/).filter(Boolean);
	if (parts.length === 0) return { first: "", last: "" };
	if (parts.length === 1) return { first: parts[0], last: "" };
	return { first: parts[0], last: parts.slice(1).join(" ") };
};

const firstAndLastFromCustomer = (customer) => {
	const first = (customer.custom_first_name || customer.first_name || "").trim();
	const last = (customer.custom_last_name || customer.last_name || "").trim();
	if (first || last) return { first, last };
	return splitCustomerName(customer.customer_name);
};

const applyCustomerToForm = (customer) => {
	if (!customer || typeof customer !== "object") return;

	if (customer.customer_name) {
		customerData.value.customer_name = customer.customer_name;
	} else if (customer.custom_first_name || customer.custom_last_name) {
		customerData.value.customer_name = [customer.custom_first_name, customer.custom_last_name]
			.filter(Boolean)
			.join(" ")
			.trim();
	}

	if (customer.email_id != null) {
		customerData.value.email_id = customer.email_id || "";
	}
	if (customer.customer_group) {
		customerData.value.customer_group = customer.customer_group;
	} else if (!customerData.value.customer_group) {
		customerData.value.customer_group = customerGroups.value[0] || "";
	}
	if (customer.territory) {
		customerData.value.territory = customer.territory;
	} else if (!customerData.value.territory) {
		customerData.value.territory =
			territories.value.find((n) => n === "All Territories") || territories.value[0] || "";
	}
	if (customer.custom_governorate != null) {
		customerData.value.custom_governorate = customer.custom_governorate || "";
	}
	if (customer.custom_district != null) {
		customerData.value.custom_district = customer.custom_district || "";
	}

	const { first, last } = firstAndLastFromCustomer(customer);
	customerData.value.custom_first_name = first;
	customerData.value.custom_last_name = last;

	if (customer.mobile_no) {
		hydrateMobileFields(customer.mobile_no);
	}
};

/** Split stored mobile into ISD + national number (supports legacy formats). */
const hydrateMobileFields = (mobile) => {
	if (!mobile) {
		phoneNumber.value = "";
		return;
	}
	customerData.value.mobile_no = mobile;
	const parsed = countriesStore.parsePhoneNumber(mobile);
	if (parsed.isd) {
		selectedCountryCode.value = parsed.isd;
		phoneNumber.value = parsed.number;
	} else {
		// Leave selectedCountryCode for applyDefaultCountryCode (profile / fallback)
		phoneNumber.value = parsed.number || mobile;
	}
};

const handleClickOutside = (event) => {
	if (showCountryDropdown.value && dropdownRef.value && !dropdownRef.value.contains(event.target)) {
		closeCountryDropdown();
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

	// Value may already be an ISD like "+20"
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
	log.info(`Set country code to ${isd} for ${profileCountry}`);
	return true;
};

/** POS Profile country (Company → country), from shift/bootstrap or API. */
const resolvePosProfileCountry = async () => {
	const fromShift = shiftStore.currentProfile?.country;
	if (fromShift) return fromShift;

	const fromBootstrap = bootstrapStore.getPreloadedPOSProfile()?.country;
	if (fromBootstrap) return fromBootstrap;

	if (!props.posProfile) return null;

	try {
		const data = await posProfileResource.reload();
		return data?.country || null;
	} catch (err) {
		log.error("Error loading POS Profile country", err);
		return null;
	}
};

/**
 * Apply a default mobile ISD once when opening the dialog, unless one is already
 * set. In create mode that's every time (no code picked yet); in edit mode it's a
 * gap-filler for customers whose stored mobile_no predates the ISD-prefix format
 * (no "-" for the customer-prop watcher to split on) — without this, such a
 * customer can never satisfy canSubmitCustomer and Save Changes stays disabled.
 * Never re-applies after open / user pick.
 */
const applyDefaultCountryCode = async () => {
	if (defaultCountryApplied.value || selectedCountryCode.value) {
		defaultCountryApplied.value = true;
		return;
	}

	await countriesStore.loadCountries();

	// Re-parse stored mobile now that ISD list is available (e.g. "+2010..." without "-")
	if (!selectedCountryCode.value && customerData.value.mobile_no) {
		hydrateMobileFields(customerData.value.mobile_no);
	}

	// Bail if cashier already picked a code while countries were loading, or parse found ISD
	if (selectedCountryCode.value) {
		defaultCountryApplied.value = true;
		if (phoneNumber.value) updateMobileNumber();
		return;
	}

	const profileCountry = await resolvePosProfileCountry();

	if (selectedCountryCode.value) {
		defaultCountryApplied.value = true;
		if (phoneNumber.value) updateMobileNumber();
		return;
	}

	const applied = setCountryFromProfileValue(profileCountry);
	if (!applied && !selectedCountryCode.value) {
		const fallback =
			resolveCountryIsd(DEFAULT_MOBILE_ISD) ||
			countriesStore.countries[0]?.isd ||
			DEFAULT_MOBILE_ISD;
		selectedCountryCode.value = fallback;
		log.warn(`Falling back to default ISD ${fallback}`);
	}
	defaultCountryApplied.value = true;
	// Legacy edit: keep Save enabled and normalize mobile once ISD is resolved
	if (phoneNumber.value) updateMobileNumber();
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
	makeParams: () => ({
		customer_name: requiresSplitCustomerName.value
			? computedCustomerName.value
			: (customerData.value.customer_name || "").trim(),
		mobile_no: customerData.value.mobile_no || "",
		email_id: customerData.value.email_id || "",
		customer_group: customerData.value.customer_group || "",
		territory: customerData.value.territory || "",
		custom_governorate: customerData.value.custom_governorate || "",
		custom_district: customerData.value.custom_district || "",
		custom_first_name: customerData.value.custom_first_name || "",
		custom_last_name: customerData.value.custom_last_name || "",
		custom_is_publish: 1,
		pos_profile: props.posProfile,
	}),
	onSuccess: async (data) => {
		if (data?.already_exists && data.existing_customer) {
			const existingName = data.existing_customer.name;
			// Editing this same customer is not a duplicate of itself.
			if (isEditMode.value && existingName && existingName === editingCustomerName.value) {
				return;
			}
			existingDuplicate.value = {
				message: data.message || __("A customer with this email already exists."),
				existing_customer: data.existing_customer,
			};
			return;
		}
		showSuccess(__("Customer {0} created successfully", [data.customer_name]));
		if (data.external_sync_error) {
			// Saved in POS, but the external system rejected it: show its message.
			showError(data.external_sync_error);
		}
		// Offer "Verify email now" when enabled (or the new customer is an F&F
		// member, who needs a verified email), online and a real email was entered
		const realEmail = hasRealEmail(data.email_id || customerData.value.email_id) && !isOffline();
		const offerVerification =
			realEmail &&
			(posSettingsStore.customerEmailVerificationEnabled ||
				(await fetchFnfMembership(data.name, props.posProfile)));
		if (offerVerification) {
			createdCustomer.value = { ...data, email_id: data.email_id || customerData.value.email_id };
			return;
		}
		emit("customer-created", data);
		show.value = false;
	},
	onError: (error) => {
		log.error("Error creating customer", error);
		// Prefer _server_messages / messages from frappe.throw (e.g. an external rejection).
		handleError(error, __("Failed to create customer"));
	},
});

const updateCustomerResource = createResource({
	url: "pos_next.api.customers.update_customer",
	makeParams: () => ({
		name: editingCustomerName.value,
		customer_name: requiresSplitCustomerName.value
			? computedCustomerName.value
			: (customerData.value.customer_name || "").trim(),
		customer_group: customerData.value.customer_group || "",
		territory: customerData.value.territory || "",
		mobile_no: customerData.value.mobile_no || "",
		email_id: customerData.value.email_id || "",
		custom_governorate: customerData.value.custom_governorate || "",
		custom_district: customerData.value.custom_district || "",
		...(requiresSplitCustomerName.value
			? {
					custom_first_name: customerData.value.custom_first_name || "",
					custom_last_name: customerData.value.custom_last_name || "",
				}
			: {}),
		pos_profile: props.posProfile,
	}),
	onSuccess: async (data) => {
		const saveAndSend = saveAndSendPending.value;
		saveAndSendPending.value = false;
		if (data?.already_exists) {
			// The new email or phone belongs to another customer: nothing was saved.
			showError(data.message || __("A customer with this email already exists."));
			return;
		}
		showSuccess(__("Customer {0} updated successfully", [data.customer_name]));
		if (data.external_sync_error) {
			// Saved in POS, but the external system rejected or could not apply the change.
			showError(data.external_sync_error);
		}
		if (saveAndSend) {
			// Stay open: record the saved email, then send the code.
			const savedEmail = data.email_id ?? customerData.value.email_id ?? "";
			savedEmailOverride.value = savedEmail;
			if (props.customer?.name) {
				emit("customer-verified", { name: props.customer.name, patch: { email_id: savedEmail } });
			}
			await nextTick();
			await verificationPanel.value?.send?.();
			return;
		}
		emit("customer-updated", data);
		show.value = false;
	},
	onError: (error) => {
		saveAndSendPending.value = false;
		log.error("Error updating customer", error);
		handleError(error, __("Failed to update customer"));
	},
});

const sellingSettingsResource = createResource({
	// A cashier cannot read Selling Settings or Customer Group: this endpoint returns the two
	// defaults and the selectable groups
	url: "pos_next.api.customers.get_customer_defaults",
	auto: false,
	onError: (err) => log.error("Error loading customer defaults", err),
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

const territoriesResource = createListResource("Territory", (names) => {
	territories.value = names;
	if (!customerData.value.territory && names.length > 0) {
		const settingsDefault = sellingSettingsResource.data?.territory;
		customerData.value.territory = pickDefault(settingsDefault, names, (list) =>
			list.find((n) => n === "All Territories")
		);
	}
});

const governoratesResource = createListResource("POS Governorate", (names) => {
	governorates.value = names;
});

const customerLocationResource = createResource({
	url: "frappe.client.get_value",
	makeParams: () => ({
		doctype: "Customer",
		filters: { name: editingCustomerName.value },
		fieldname: ["custom_governorate", "custom_district"],
	}),
	auto: false,
	onSuccess: (data) => {
		customerData.value.custom_governorate = data?.custom_governorate || "";
		customerData.value.custom_district = data?.custom_district || "";
	},
	onError: (err) => log.error("Error loading customer location", err),
});

const customerDetailsResource = createResource({
	url: "pos_next.api.customers.get_customer_details",
	makeParams: () => ({ customer: editingCustomerName.value }),
	auto: false,
	onSuccess: (data) => {
		if (!data) return;
		if (editingCustomerName.value && data.name && data.name !== editingCustomerName.value) {
			return;
		}
		applyCustomerToForm(data);
	},
	onError: (err) => log.error("Error loading customer details", err),
});

const districtsResource = createResource({
	url: "frappe.client.get_list",
	makeParams: () => ({
		doctype: "POS District",
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

const loadFreshVerification = async () => {
	freshVerification.value = null;
	fnfMember.value = false;
	if (!props.customer?.name || isOffline()) return;
	const name = props.customer.name;
	const [status, member] = await Promise.all([
		fetchVerificationStatus(name),
		posSettingsStore.customerEmailVerificationEnabled
			? Promise.resolve(false)
			: fetchFnfMembership(name, props.posProfile),
	]);
	if (props.customer?.name !== name) return;
	if (status) freshVerification.value = status;
	fnfMember.value = member;
};

/** Customer Group list and default come from the endpoint: a cashier cannot read the doctype */
const applyCustomerGroups = () => {
	const data = sellingSettingsResource.data;
	const names = data?.customer_groups || [];
	if (!names.length) return;
	customerGroups.value = names;
	if (!customerData.value.customer_group) {
		customerData.value.customer_group = pickDefault(data.customer_group, names);
	}
};

const loadDialogData = async () => {
	loadFreshVerification();
	// One failing resource must not stop the others: each is guarded and logs its own error
	try {
		await sellingSettingsResource.reload();
	} catch (err) {
		log.error("Error loading customer defaults", err);
	}

	if (!isEditMode.value) {
		customerData.value.customer_group = "";
		customerData.value.territory = "";
	}
	applyCustomerGroups();

	// Load form options + countries (awaited so ISD map is ready before default)
	await Promise.allSettled([
		countriesStore.loadCountries().catch((err) => log.error("Error loading countries", err)),
		territoriesResource.reload(),
		governoratesResource.reload(),
	]);
	if (isEditMode.value && editingCustomerName.value) {
		await Promise.allSettled([
			customerDetailsResource.reload(),
			customerLocationResource.reload(),
		]);
	}
	if (customerData.value.custom_governorate) {
		try {
			await districtsResource.reload();
		} catch (err) {
			log.error("Error loading districts", err);
		}
	}
	checkPermissions();

	// Default mobile country code from POS Profile → Company country
	try {
		await applyDefaultCountryCode();
	} catch (err) {
		log.error("Error applying default country code", err);
	}
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

const handleEmailVerified = async ({ verified_email }) => {
	const patch = {
		custom_email_verified: 1,
		custom_verified_email: verified_email,
		custom_email_verified_on: new Date().toISOString(),
	};
	verifiedOverride.value = patch;
	// Let the parent refresh the (stale) edit/selected-cart customer objects
	if (props.customer?.name) emit("customer-verified", { name: props.customer.name, patch });
	const base = createdCustomer.value || props.customer;
	if (createdCustomer.value) createdCustomer.value = { ...createdCustomer.value, ...patch };
	// Keep the POS customer cache in sync without closing/selecting anything
	try {
		if (base?.name) await customerSearchStore.addCustomerToCache({ ...base, ...patch });
	} catch (err) {
		log.error("Failed to refresh customer cache after verification", err);
	}
};

const finishCreated = () => {
	const created = createdCustomer.value;
	if (
		emailVerificationLocked.value &&
		!window.confirm(__("Email verification is in progress. Leave without verifying?"))
	) {
		return;
	}
	createdCustomer.value = null;
	emailVerificationLocked.value = false;
	if (created) emit("customer-created", created);
	show.value = false;
};

/** Checks the required fields, shows each message under its field and focuses the first one. */
const validateForm = () => {
	const errors = {};
	if (requiresSplitCustomerName.value) {
		if (!customerData.value.custom_first_name?.trim()) {
			errors.custom_first_name = __("First Name is required");
		}
		if (!customerData.value.custom_last_name?.trim()) {
			errors.custom_last_name = __("Last Name is required");
		}
	} else if (!customerData.value.customer_name?.trim()) {
		errors.customer_name = __("Customer Name is required");
	}
	if (!phoneNumber.value) {
		errors.mobile = __("Mobile Number is required");
	} else if (!selectedCountryCode.value) {
		errors.country = __("Choose a country code");
	}
	fieldErrors.value = errors;
	const first = Object.keys(errors)[0];
	if (!first) return true;
	const target = {
		customer_name: ids.name,
		custom_first_name: ids.first,
		custom_last_name: ids.last,
		mobile: ids.phone,
	}[first];
	nextTick(() => {
		if (first === "country") countryButtonRef.value?.focus();
		else if (target) document.getElementById(target)?.focus();
	});
	return false;
};

// A message goes away as soon as its field is filled in
const clearFieldError = (key) => {
	if (fieldErrors.value[key]) {
		const { [key]: _removed, ...rest } = fieldErrors.value;
		fieldErrors.value = rest;
	}
};
watch(() => customerData.value.customer_name, () => clearFieldError("customer_name"));
watch(() => customerData.value.custom_first_name, () => clearFieldError("custom_first_name"));
watch(() => customerData.value.custom_last_name, () => clearFieldError("custom_last_name"));
watch(phoneNumber, () => clearFieldError("mobile"));
watch(selectedCountryCode, () => clearFieldError("country"));

/** Panel "Save email & send code": save the customer, keep the dialog open, then send. */
const handleSaveAndSend = async () => {
	if (!isEditMode.value || !editingCustomerName.value || !validateForm()) return;
	saveAndSendPending.value = true;
	await updateCustomerResource.submit();
};

const handleCreate = async () => {
	if (
		emailVerificationLocked.value &&
		!window.confirm(__("Email verification is in progress. Leave without verifying?"))
	) {
		return;
	}
	if (!validateForm()) return;
	if (isEditMode.value && editingCustomerName.value) {
		await updateCustomerResource.submit();
		return;
	}
	await createCustomerResource.submit();
};

const selectExistingCustomer = () => {
	const customer = existingDuplicate.value?.existing_customer;
	existingDuplicate.value = null;
	if (customer) emit("customer-created", customer);
	show.value = false;
};

const clearExistingDuplicate = () => {
	existingDuplicate.value = null;
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
	phoneNumber.value = "";
	defaultCountryApplied.value = false;
	existingDuplicate.value = null;
	fieldErrors.value = {};
	closeCountryDropdown();
};

// =============================================================================
// Watchers
// =============================================================================

watch(
	() => props.initialName,
	(name) => name && (customerData.value.customer_name = name)
);

// Pre-fill form when customer prop changes (edit mode)
watch(
	() => props.customer,
	(customer) => {
		if (customer && typeof customer === "object" && customer.name) {
			applyCustomerToForm(customer);
		}
	},
	{ immediate: true }
);

watch(
	() => customerData.value.mobile_no,
	(value) => {
		// Only sync from stored mobile when editing; never overwrite create-mode default
		if (!isEditMode.value || !value) return;
		const parsed = countriesStore.parsePhoneNumber(value);
		if (!parsed.isd) return;
		selectedCountryCode.value = parsed.isd;
		phoneNumber.value = parsed.number;
	}
);

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
		countryHighlight.value = Math.max(
			0,
			filteredCountries.value.findIndex((c) => c.isd === selectedCountryCode.value)
		);
		await nextTick();
		countrySearchRef.value?.focus();
		scrollHighlightIntoView();
	}
});

watch(countrySearchQuery, () => (countryHighlight.value = 0));

watch(
	() => props.modelValue,
	async (isOpen) => {
		if (isOpen) return await loadDialogData();
		// Closed (X / Esc) while the post-create verify step was open: still hand the customer over
		if (createdCustomer.value) {
			const created = createdCustomer.value;
			createdCustomer.value = null;
			emit("customer-created", created);
		}
		emailVerificationLocked.value = false;
		verifiedOverride.value = null;
		freshVerification.value = null;
		savedEmailOverride.value = null;
		saveAndSendPending.value = false;
		resetForm();
	}
);

// =============================================================================
// Lifecycle Hooks
// =============================================================================

onMounted(() => {
	document.addEventListener("click", handleClickOutside);
});

onBeforeUnmount(() => {
	document.removeEventListener("click", handleClickOutside);
});
</script>

<style>
/* frappe-ui's header close button is 28px: bring it to the POS touch target, in this dialog only */
.dialog-content:has([data-testid="customer-dialog-body"]) .mb-6.justify-between > button {
	min-width: var(--pos-target);
	min-height: var(--pos-target);
}
</style>
