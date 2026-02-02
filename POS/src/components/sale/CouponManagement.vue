<template>
	<!-- Split Layout matching PromotionManagement -->
	<div class="flex-1 flex overflow-hidden">
		<!-- LEFT SIDE: Coupon List & Navigation -->
		<div class="w-80 flex-shrink-0 border-e bg-gray-50 flex flex-col">
			<!-- Search & Filter -->
			<div class="p-4 bg-white border-b flex flex-col gap-3">
				<FormControl
					type="text"
					v-model="searchQuery"
					:placeholder="__('Search coupons...')"
				>
					<template #prefix>
						<FeatherIcon name="search" class="w-4 h-4 text-gray-500" />
					</template>
				</FormControl>

				<div class="grid grid-cols-2 gap-2">
					<FormControl
						type="select"
						v-model="filterStatus"
						:options="[
							{ label: __('All Status'), value: 'all' },
							{ label: __('Active Only'), value: 'active' },
							{ label: __('Expired'), value: 'expired' },
							{ label: __('Not Started'), value: 'not_started' },
							{ label: __('Exhausted'), value: 'exhausted' },
							{ label: __('Disabled'), value: 'disabled' }
						]"
					/>
					<FormControl
						type="select"
						v-model="filterType"
						:options="[
							{ label: __('All Types'), value: 'all' },
							{ label: __('Promotional'), value: 'Promotional' },
							{ label: __('Gift Card'), value: 'Gift Card' }
						]"
					/>
				</div>
			</div>

			<!-- Create New Button -->
			<div class="p-4 bg-white border-b flex flex-col gap-2">
				<Button
					v-if="permissions.create"
					@click="handleCreateNew"
					variant="solid"
					class="w-full"
				>
					<template #prefix>
						<FeatherIcon name="plus-circle" class="w-4 h-4" />
					</template>
					{{ __('Create New Coupon') }}
				</Button>
				<Button
					@click="loadCoupons"
					variant="outline"
					class="w-full"
					:loading="loading"
				>
					<template #prefix>
						<FeatherIcon name="refresh-cw" class="w-4 h-4" />
					</template>
					{{ __('Refresh') }}
				</Button>
			</div>

			<!-- Coupons List -->
			<div class="flex-1 overflow-y-auto">
				<!-- Loading State -->
				<div v-if="loading && coupons.length === 0" class="flex items-center justify-center py-12">
					<div class="text-center">
						<LoadingIndicator class="w-6 h-6 mx-auto mb-2" />
						<p class="text-sm text-gray-600">{{ __('Loading...') }}</p>
					</div>
				</div>

				<!-- Empty State -->
				<div v-else-if="filteredCoupons.length === 0" class="text-center py-12 px-4">
					<div class="text-gray-400 mb-3">
						<FeatherIcon name="gift" class="w-12 h-12 mx-auto" />
					</div>
					<p class="text-sm text-gray-600">{{ __('No coupons found') }}</p>
				</div>

				<!-- Coupon Items -->
				<div v-else class="p-2 flex flex-col gap-1">
					<button
						v-for="coupon in filteredCoupons"
						:key="coupon.name"
						@click="handleSelectCoupon(coupon)"
						:class="[
							'w-full text-start p-3 rounded-md transition-all',
							selectedCoupon?.name === coupon.name
								? 'bg-blue-50 ring-2 ring-blue-500 ring-inset'
								: 'hover:bg-gray-100'
						]"
					>
						<div class="flex items-start justify-between mb-2">
							<div class="flex-1 min-w-0">
								<div class="flex items-center gap-2">
									<p :class="[
										'text-sm font-medium truncate',
										selectedCoupon?.name === coupon.name ? 'text-blue-900' : 'text-gray-900'
									]">
										{{ coupon.coupon_code }}
									</p>
									<Badge
										v-if="coupon.coupon_type === 'Gift Card'"
										variant="subtle"
										theme="purple"
										size="sm"
									>
										{{ __('Gift') }}
									</Badge>
								</div>
								<p class="text-xs text-gray-500 mt-0.5 truncate">{{ coupon.coupon_name }}</p>
							</div>
							<Badge
								variant="subtle"
								:theme="getStatusTheme(coupon.status)"
								size="sm"
							>
								{{ coupon.status || __('Active') }}
							</Badge>
						</div>
						<div class="flex items-center justify-between text-xs">
							<span class="text-gray-500">
								{{ coupon.maximum_use 
									? __('Used: {0}/{1}', [coupon.used, coupon.maximum_use])
									: __('Used: {0}', [coupon.used]) }}
							</span>
							<span class="text-gray-500">
								{{ coupon.valid_upto ? formatDate(coupon.valid_upto) : __('No expiry') }}
							</span>
						</div>
					</button>
				</div>
			</div>
		</div>

		<!-- RIGHT SIDE: Work Area -->
		<div class="flex-1 overflow-y-auto bg-white">
			<!-- Empty State: No Selection -->
			<div v-if="!selectedCoupon && !isCreating" class="flex items-center justify-center h-full">
				<div class="text-center px-8 max-w-md">
					<div class="text-gray-300 mb-4">
						<FeatherIcon name="gift" class="w-16 h-16 mx-auto" />
					</div>
					<h3 class="text-xl font-semibold text-gray-900 mb-2">{{ __('Select a Coupon') }}</h3>
					<p class="text-sm text-gray-600 mb-6">{{ __('Choose a coupon from the list to view and edit, or create a new one to get started') }}</p>
					<Button
						v-if="permissions.create"
						@click="handleCreateNew"
						variant="solid"
					>
						<template #prefix>
							<FeatherIcon name="plus" class="w-4 h-4" />
						</template>
						{{ __('Create New Coupon') }}
					</Button>
					<p v-else class="text-sm text-amber-600">
						{{ __("You don't have permission to create coupons") }}
					</p>
				</div>
			</div>

			<!-- Create/Edit Form -->
			<div v-else class="p-6">
				<div class="max-w-5xl mx-auto">
					<!-- Form Header -->
					<div class="flex items-center justify-between mb-6 pb-4 border-b">
						<div>
							<div class="flex items-center gap-3">
								<h3 class="text-xl font-semibold text-gray-900">
									{{ isCreating ? __('Create New Coupon') : __('Coupon Details') }}
								</h3>
								<Badge
									v-if="!isCreating && selectedCoupon?.coupon_type"
									variant="subtle"
									:theme="selectedCoupon.coupon_type === 'Gift Card' ? 'purple' : 'blue'"
									size="md"
								>
									{{ selectedCoupon.coupon_type }}
								</Badge>
							</div>
							<p class="text-sm text-gray-600 mt-1">
								{{ isCreating ? __('Fill in the details to create a new coupon') : __('View and update coupon information') }}
							</p>
						</div>
						<div class="flex items-center gap-2">
							<Button
								v-if="!isCreating && permissions.write"
								@click="handleToggle"
								variant="outline"
								:theme="couponDetails.disabled ? 'green' : 'orange'"
							>
								<template #prefix>
									<FeatherIcon :name="couponDetails.disabled ? 'check-circle' : 'x-circle'" class="w-4 h-4" />
								</template>
								{{ couponDetails.disabled ? __('Enable') : __('Disable') }}
							</Button>
							<Button
								v-if="!isCreating && permissions.delete && selectedCoupon.used === 0"
								@click="handleDelete"
								variant="ghost"
								theme="red"
							>
								<template #prefix>
									<FeatherIcon name="trash-2" class="w-4 h-4" />
								</template>
								{{ __('Delete') }}
							</Button>
							<div v-if="!isCreating && (permissions.write || permissions.delete)" class="w-px h-6 bg-gray-200"></div>
							<Button
								@click="handleCancel"
								variant="ghost"
							>
								{{ __('Cancel') }}
							</Button>
							<Button
								v-if="isCreating ? permissions.create : permissions.write"
								@click="handleSubmit"
								:loading="loading"
								variant="solid"
							>
								<template #prefix>
									<FeatherIcon :name="isCreating ? 'plus' : 'save'" class="w-4 h-4" />
								</template>
								{{ isCreating ? __('Create') : __('Update') }}
							</Button>
						</div>
					</div>

					<!-- Form Content -->
					<div class="flex flex-col gap-6">
						<!-- Basic Information Card -->
						<Card>
							<div class="p-5">
								<div class="flex items-center gap-2 mb-4">
									<FeatherIcon name="info" class="w-4 h-4 text-blue-600" />
									<h4 class="text-sm font-semibold text-gray-900">{{ __('Basic Information') }}</h4>
								</div>
								<div class="grid grid-cols-2 gap-4">
									<div class="col-span-2">
										<FormControl
											type="text"
											:label="__('Coupon Name')"
											v-model="form.coupon_name"
											:disabled="!isCreating"
											:placeholder="__('e.g., Summer Sale Coupon 2025')"
											required
										/>
									</div>

									<FormControl
										type="select"
										:label="__('Coupon Type')"
										v-model="form.coupon_type"
										:disabled="!isCreating"
										:options="[
											{ label: __('Promotional'), value: 'Promotional' },
											{ label: __('Gift Card'), value: 'Gift Card' }
										]"
										required
									/>

									<FormControl
										type="text"
										:label="__('Coupon Code')"
										v-model="form.coupon_code"
										:disabled="!isCreating"
										:placeholder="__('Auto-generated if empty')"
									>
										<template #suffix v-if="isCreating">
											<Button
												size="sm"
												variant="ghost"
												@click="generateCouponCode"
											>
												{{ __('Generate') }}
											</Button>
										</template>
									</FormControl>

									<!-- Customer field for Gift Cards -->
									<div v-if="form.coupon_type === 'Gift Card'" class="col-span-2">
										<div v-if="isCreating">
											<label class="block text-xs font-medium text-gray-500 mb-1.5">{{ __('Customer') }} <span class="text-red-500">*</span></label>
											<AutocompleteSelect
												v-model="form.customer"
												:options="customerOptions"
												:loading="customerLoading"
												:placeholder="__('Search customer by name or mobile...')"
												@search="handleCustomerSearch"
												required
											/>
										</div>
										<div v-else>
											<label class="block text-sm font-medium text-gray-700 mb-2 text-start">{{ __('Customer') }}</label>
											<div class="px-3 py-2 bg-gray-50 rounded-lg">
												<p class="text-sm font-medium text-gray-900">{{ couponDetails.customer_name || couponDetails.customer }}</p>
												<p class="text-xs text-gray-500">{{ couponDetails.customer }}</p>
											</div>
										</div>
									</div>

									<FormControl
										v-if="campaigns.length > 0"
										type="select"
										:label="__('Campaign')"
										v-model="form.campaign"
										:disabled="!isCreating"
										:options="campaignOptions"
									/>

									<!-- Company field -->
									<div>
										<label class="block text-sm font-medium text-gray-700 mb-2 text-start">{{ __('Company') }}</label>
										<div class="px-3 py-2 bg-gray-50 rounded-lg">
											<p class="text-sm text-gray-900">{{ isCreating ? props.company : couponDetails.company }}</p>
										</div>
									</div>

									<!-- Referral Code (view only when editing) -->
									<div v-if="!isCreating && couponDetails.referral_code">
										<label class="block text-sm font-medium text-gray-700 mb-2 text-start">{{ __('Referral Code') }}</label>
										<div class="px-3 py-2 bg-blue-50 rounded-lg border border-blue-200">
											<p class="text-sm font-medium text-blue-900">{{ couponDetails.referral_code }}</p>
										</div>
									</div>
								</div>
							</div>
						</Card>

						<!-- Discount Configuration Card -->
						<Card>
							<div class="p-5">
								<div class="flex items-center gap-2 mb-4">
									<FeatherIcon name="percent" class="w-4 h-4 text-purple-600" />
									<h4 class="text-sm font-semibold text-gray-900">{{ __('Discount Configuration') }}</h4>
								</div>
								<div class="grid grid-cols-2 gap-4">
									<FormControl
										type="select"
										:label="__('Discount Type')"
										v-model="form.discount_type"
										:options="[
											{ label: __('Percentage'), value: 'Percentage' },
											{ label: __('Amount'), value: 'Amount' }
										]"
										required
									/>

									<FormControl
										type="select"
										:label="__('Apply Discount On')"
										v-model="form.apply_on"
										:options="[
											{ label: __('Grand Total'), value: 'Grand Total' },
											{ label: __('Net Total'), value: 'Net Total' }
										]"
										required
									/>

									<FormControl
										v-if="form.discount_type === 'Percentage'"
										type="number"
										:label="__('Discount Percentage (%)')"
										v-model="form.discount_percentage"
										:placeholder="__('e.g., 20')"
										:min="0"
										:max="100"
										required
									/>

									<FormControl
										v-if="form.discount_type === 'Amount'"
										type="number"
										:label="__('Discount Amount')"
										v-model="form.discount_amount"
										:placeholder="__('Amount in {0}', [currency])"
										:min="0"
										required
									/>

									<FormControl
										type="number"
										:label="__('Minimum Cart Amount')"
										v-model="form.min_amount"
										:placeholder="__('Optional minimum in {0}', [currency])"
										:min="0"
									/>

									<FormControl
										type="number"
										:label="__('Maximum Discount Amount')"
										v-model="form.max_amount"
										:placeholder="__('Optional cap in {0}', [currency])"
										:min="0"
									/>
								</div>
								<div v-if="!isCreating && couponDetails.discount_type" class="mt-4 p-3 bg-purple-50 rounded-lg">
									<p class="text-sm text-gray-700">
										<strong>{{ __('Current Discount:') }}</strong>
										<span v-if="couponDetails.discount_type === 'Percentage'">
											{{ __('{0}% off {1}', [Number(couponDetails.discount_percentage).toFixed(2), couponDetails.apply_on]) }}
										</span>
										<span v-else>
											{{ __('{0} off {1}', [formatCurrency(couponDetails.discount_amount), couponDetails.apply_on]) }}
										</span>
										<span v-if="couponDetails.min_amount" class="ms-2">
											{{ __('(Min: {0})', [formatCurrency(couponDetails.min_amount)]) }}
										</span>
										<span v-if="couponDetails.max_amount" class="ms-2">
											{{ __('(Max Discount: {0})', [formatCurrency(couponDetails.max_amount)]) }}
										</span>
									</p>
								</div>
							</div>
						</Card>

						<!-- Validity & Usage Card -->
						<Card>
							<div class="p-5">
								<div class="flex items-center gap-2 mb-4">
									<FeatherIcon name="calendar" class="w-4 h-4 text-green-600" />
									<h4 class="text-sm font-semibold text-gray-900">{{ __('Validity & Usage') }}</h4>
								</div>
								<div class="grid grid-cols-3 gap-4">
									<FormControl
										type="date"
										:label="__('Valid From')"
										v-model="form.valid_from"
									/>
									<FormControl
										type="date"
										:label="__('Valid Until')"
										v-model="form.valid_upto"
									/>
									<FormControl
										v-if="form.coupon_type === 'Promotional'"
										type="number"
										:label="__('Maximum Use')"
										v-model="form.maximum_use"
										:placeholder="__('Unlimited')"
									/>
									<div v-if="!isCreating">
										<label class="block text-sm font-medium text-gray-700 mb-2 text-start">{{ __('Times Used') }}</label>
										<div class="px-3 py-2 bg-gray-50 rounded-lg">
											<p class="text-lg font-bold text-gray-900">{{ couponDetails.used || 0 }}</p>
										</div>
									</div>
								</div>
								<div class="mt-4">
									<label class="flex items-center gap-2">
										<input
											type="checkbox"
											v-model="form.one_use"
											class="rounded border-gray-300"
										/>
										<span class="text-sm text-gray-700">{{ __('Only One Use Per Customer') }}</span>
									</label>
								</div>
							</div>
						</Card>

						<!-- Coupon Status & Info (View Only) -->
						<Card v-if="!isCreating">
							<div class="p-5">
								<div class="flex items-center gap-2 mb-4">
									<FeatherIcon name="activity" class="w-4 h-4 text-orange-600" />
									<h4 class="text-sm font-semibold text-gray-900">{{ __('Coupon Status & Info') }}</h4>
								</div>
								<div class="grid grid-cols-3 gap-4">
									<div>
										<label class="block text-xs font-medium text-gray-500 mb-1 text-start">{{ __('Current Status') }}</label>
										<Badge :theme="getStatusTheme(selectedCoupon.status)" variant="subtle" size="md">
											{{ selectedCoupon.status }}
										</Badge>
									</div>
									<div>
										<label class="block text-xs font-medium text-gray-500 mb-1 text-start">{{ __('Created On') }}</label>
										<p class="text-sm text-gray-900">{{ formatDate(couponDetails.creation) }}</p>
									</div>
									<div>
										<label class="block text-xs font-medium text-gray-500 mb-1 text-start">{{ __('Last Modified') }}</label>
										<p class="text-sm text-gray-900">{{ formatDate(couponDetails.modified) }}</p>
									</div>
									<div v-if="couponDetails.email_id">
										<label class="block text-xs font-medium text-gray-500 mb-1 text-start">{{ __('Email') }}</label>
										<p class="text-sm text-gray-900">{{ couponDetails.email_id }}</p>
									</div>
									<div v-if="couponDetails.mobile_no">
										<label class="block text-xs font-medium text-gray-500 mb-1 text-start">{{ __('Mobile') }}</label>
										<p class="text-sm text-gray-900">{{ couponDetails.mobile_no }}</p>
									</div>
								</div>
							</div>
						</Card>
					</div>
				</div>
			</div>
		</div>
	</div>

	<!-- Delete Confirmation Dialog -->
	<Transition name="fade">
		<div
			v-if="showDeleteConfirm"
			class="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[400]"
			@click.self="showDeleteConfirm = false"
		>
			<div class="bg-white rounded-lg shadow-2xl max-w-md w-full mx-4 p-6">
				<div class="flex items-start gap-4">
					<div class="flex-shrink-0">
						<div class="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center">
							<FeatherIcon name="alert-triangle" class="w-6 h-6 text-red-600" />
						</div>
					</div>
					<div class="flex-1">
						<h3 class="text-lg font-semibold text-gray-900 mb-2">{{ __('Delete Coupon') }}</h3>
							<TranslatedHTML 
								:tag="'p'"
								class="text-sm text-gray-600 mb-1"
								:inner="__('Are you sure you want to delete &lt;strong&gt;&quot;{0}&quot;&lt;strong&gt;?', [selectedCoupon?.coupon_code])"
							/>
						<p class="text-sm text-gray-500">
							{{ __('This action cannot be undone.') }}
						</p>
					</div>
				</div>
				<div class="flex justify-end gap-3 mt-6">
					<Button
						@click="showDeleteConfirm = false"
						variant="ghost"
					>
						{{ __('Cancel') }}
					</Button>
					<Button
						@click="confirmDelete"
						variant="solid"
						theme="red"
						:loading="loading"
					>
						<template #prefix>
							<FeatherIcon name="trash-2" class="w-4 h-4" />
						</template>
						{{ __('Delete Coupon') }}
					</Button>
				</div>
			</div>
		</div>
	</Transition>
</template>

<script setup>
import AutocompleteSelect from "@/components/common/AutocompleteSelect.vue"
import { useToast } from "@/composables/useToast"
import { useCustomerSearchStore } from "@/stores/customerSearch"
import { usePOSSettingsStore } from "@/stores/posSettings"
import { DEFAULT_CURRENCY, DEFAULT_LOCALE } from "@/utils/currency"
import { Badge, Button, Card, FormControl, LoadingIndicator, createResource } from "frappe-ui"
import { FeatherIcon } from "frappe-ui"
import { storeToRefs } from "pinia"
import { computed, onMounted, ref, watch } from "vue"
import TranslatedHTML from "../common/TranslatedHTML.vue"

const { showSuccess, showError, showWarning } = useToast()
const customerStore = useCustomerSearchStore()
const { filteredCustomers, loading: customerLoading } = storeToRefs(customerStore)
const posSettingsStore = usePOSSettingsStore()

const props = defineProps({
	company: String,
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
	permissions: {
		type: Object,
		default: () => ({
			create: true,
			write: true,
			delete: true,
		}),
	},
})

const emit = defineEmits(["coupon-saved", "refresh-requested"])

const loading = ref(false)
const coupons = ref([])
const selectedCoupon = ref(null)
const couponDetails = ref({})
const isCreating = ref(false)
const showDeleteConfirm = ref(false)

// Filters
const searchQuery = ref("")
const filterStatus = ref("all")
const filterType = ref("all")

// Data for dropdowns
const campaigns = ref([])

// Form
const form = ref({
	coupon_name: "",
	coupon_type: "Promotional",
	coupon_code: "",
	discount_type: "Percentage",
	discount_percentage: null,
	discount_amount: null,
	min_amount: null,
	max_amount: null,
	apply_on: "Grand Total",
	customer: "",
	campaign: "",
	valid_from: "",
	valid_upto: "",
	maximum_use: null,
	one_use: 0,
	company: props.company,
})

// Computed
const filteredCoupons = computed(() => {
	let filtered = coupons.value

	// Filter by search query
	if (searchQuery.value) {
		const term = searchQuery.value.toLowerCase()
		filtered = filtered.filter((c) =>
			c.coupon_code?.toLowerCase().includes(term) ||
			c.coupon_name?.toLowerCase().includes(term) ||
			c.customer_name?.toLowerCase().includes(term)
		)
	}

	// Filter by status
	if (filterStatus.value !== "all") {
		filtered = filtered.filter((c) => {
			const status = c.status.toLowerCase().replace(" ", "_")
			return status === filterStatus.value
		})
	}

	// Filter by type
	if (filterType.value !== "all") {
		filtered = filtered.filter((c) => c.coupon_type === filterType.value)
	}

	return filtered
})

const campaignOptions = computed(() => {
	return [
		{ label: __("-- No Campaign --"), value: "" },
		...campaigns.value.map(c => ({ label: c.name, value: c.name }))
	]
})

const customerOptions = computed(() => {
	return filteredCustomers.value.map((c) => ({
		label: c.customer_name,
		value: c.name,
		subtitle: c.mobile_no || c.email_id,
	}))
})

// Resources
const couponsResource = createResource({
	url: "pos_next.api.promotions.get_coupons",
	makeParams() {
		return {
			company: props.company,
			include_disabled: true,
		}
	},
	auto: false,
	onSuccess(data) {
		coupons.value = data || []
		loading.value = false
	},
	onError(error) {
		loading.value = false
		handleError(error, __('Failed to load coupons'))
	},
})

const couponDetailsResource = createResource({
	url: "pos_next.api.promotions.get_coupon_details",
	makeParams() {
		return { coupon_name: selectedCoupon.value?.name }
	},
	auto: false,
	onSuccess(data) {
		couponDetails.value = data || {}
		populateFormFromCoupon(data)
		loading.value = false
	},
	onError(error) {
		loading.value = false
		handleError(error, __('Failed to load coupon details'))
	},
})

const campaignsResource = createResource({
	url: "frappe.client.get_list",
	makeParams() {
		return {
			doctype: "Campaign",
			fields: ["name"],
			filters: { disabled: 0 },
			limit_page_length: 999,
		}
	},
	auto: false,
	onSuccess(data) {
		campaigns.value = data || []
	},
})

const createCouponResource = createResource({
	url: "pos_next.api.promotions.create_coupon",
	makeParams() {
		return { data: JSON.stringify(form.value) }
	},
	auto: false,
	onSuccess(data) {
		loading.value = false
		const responseData = data?.message || data
		showSuccess(responseData?.message || __("Coupon created successfully"))
		loadCoupons()
		handleCancel()
		emit("coupon-saved", responseData)
	},
	onError(error) {
		loading.value = false
		handleError(error, __("Failed to create coupon"))
	},
})

const updateCouponResource = createResource({
	url: "pos_next.api.promotions.update_coupon",
	makeParams() {
		return {
			coupon_name: selectedCoupon.value?.name,
			data: JSON.stringify({
				discount_type: form.value.discount_type,
				discount_percentage: form.value.discount_percentage,
				discount_amount: form.value.discount_amount,
				min_amount: form.value.min_amount,
				max_amount: form.value.max_amount,
				apply_on: form.value.apply_on,
				valid_from: form.value.valid_from,
				valid_upto: form.value.valid_upto,
				maximum_use: form.value.maximum_use,
				one_use: form.value.one_use,
			}),
		}
	},
	auto: false,
	onSuccess(data) {
		loading.value = false
		const responseData = data?.message || data
		showSuccess(responseData?.message || __("Coupon updated successfully"))
		loadCoupons()
		// Reload details to show updated info
		couponDetailsResource.reload()
	},
	onError(error) {
		loading.value = false
		handleError(error, __("Failed to update coupon"))
	},
})

const toggleCouponResource = createResource({
	url: "pos_next.api.promotions.toggle_coupon",
	makeParams() {
		return { coupon_name: selectedCoupon.value?.name }
	},
	auto: false,
	onSuccess(data) {
		loading.value = false
		const responseData = data?.message || data
		showSuccess(responseData?.message || __("Coupon status updated successfully"))
		loadCoupons()
		// Reload details to get updated disabled status
		if (selectedCoupon.value) {
			couponDetailsResource.reload()
		}
	},
	onError(error) {
		loading.value = false
		handleError(error, __("Failed to toggle coupon status"))
	},
})

const deleteCouponResource = createResource({
	url: "pos_next.api.promotions.delete_coupon",
	makeParams() {
		return { coupon_name: selectedCoupon.value?.name }
	},
	auto: false,
	onSuccess(data) {
		loading.value = false
		showDeleteConfirm.value = false
		const responseData = data?.message || data
		showSuccess(responseData?.message || __("Coupon deleted successfully"))
		loadCoupons()
		handleCancel()
	},
	onError(error) {
		loading.value = false
		showDeleteConfirm.value = false
		handleError(error, __("Failed to delete coupon"))
	},
})

// Watchers
watch(() => selectedCoupon.value, (val) => {
	if (val && !isCreating.value) {
		loading.value = true
		couponDetailsResource.reload()
	}
})

onMounted(() => {
	loadCoupons()
	loadCampaigns()
	if (posSettingsStore.settings.pos_profile) {
		customerStore.loadAllCustomers(posSettingsStore.settings.pos_profile)
	}
})

// Methods
function handleCustomerSearch(query) {
	customerStore.setSearchTerm(query)
}

function loadCoupons() {
	loading.value = true
	couponsResource.reload()
}

function loadCampaigns() {
	campaignsResource.reload()
}

function handleCreateNew() {
	resetForm()
	isCreating.value = true
	selectedCoupon.value = null
}

function handleSelectCoupon(coupon) {
	if (isCreating.value) return
	selectedCoupon.value = coupon
}

function handleCancel() {
	isCreating.value = false
	selectedCoupon.value = null
	resetForm()
}

function handleSubmit() {
	// Validate
	if (!form.value.coupon_name) {
		showWarning(__("Please enter a coupon name"))
		return
	}
	if (!form.value.discount_type) {
		showWarning(__("Please select a discount type"))
		return
	}
	if (form.value.discount_type === "Percentage") {
		if (!form.value.discount_percentage || form.value.discount_percentage <= 0 || form.value.discount_percentage > 100) {
			showWarning(__("Please enter a valid discount percentage (1-100)"))
			return
		}
	} else if (form.value.discount_type === "Amount") {
		if (!form.value.discount_amount || form.value.discount_amount <= 0) {
			showWarning(__("Please enter a valid discount amount"))
			return
		}
	}
	if (form.value.coupon_type === "Gift Card" && !form.value.customer) {
		showWarning(__("Please select a customer for gift card"))
		return
	}

	loading.value = true

	if (isCreating.value) {
		createCouponResource.reload()
	} else {
		updateCouponResource.reload()
	}
}

function handleToggle() {
	loading.value = true
	toggleCouponResource.reload()
}

function handleDelete() {
	if (selectedCoupon.value.used > 0) {
		showWarning(__('Cannot delete coupon as it has been used {0} times', [selectedCoupon.value.used]))
		return
	}
	showDeleteConfirm.value = true
}

function confirmDelete() {
	loading.value = true
	deleteCouponResource.reload()
}

function generateCouponCode() {
	const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
	let code = ""
	for (let i = 0; i < 8; i++) {
		code += chars.charAt(Math.floor(Math.random() * chars.length))
	}
	form.value.coupon_code = code
}

function resetForm() {
	form.value = {
		coupon_name: "",
		coupon_type: "Promotional",
		coupon_code: "",
		discount_type: "Percentage",
		discount_percentage: null,
		discount_amount: null,
		min_amount: null,
		max_amount: null,
		apply_on: "Grand Total",
		customer: "",
		campaign: "",
		valid_from: "",
		valid_upto: "",
		maximum_use: null,
		one_use: 0,
		company: props.company,
	}
}

function populateFormFromCoupon(coupon) {
	form.value = {
		coupon_name: coupon.coupon_name || "",
		coupon_type: coupon.coupon_type || __('Promotional'),
		coupon_code: coupon.coupon_code || "",
		discount_type: coupon.discount_type || __('Percentage'),
		discount_percentage: coupon.discount_percentage || null,
		discount_amount: coupon.discount_amount || null,
		min_amount: coupon.min_amount || null,
		max_amount: coupon.max_amount || null,
		apply_on: coupon.apply_on || __('Grand Total'),
		customer: coupon.customer || "",
		campaign: coupon.campaign || "",
		valid_from: coupon.valid_from || "",
		valid_upto: coupon.valid_upto || "",
		maximum_use: coupon.maximum_use || null,
		one_use: coupon.one_use || 0,
		company: coupon.company || props.company,
	}
}

function formatDate(dateStr) {
	if (!dateStr) return ""
	const date = new Date(dateStr)
	return date.toLocaleDateString(DEFAULT_LOCALE, {
		month: "short",
		day: "numeric",
		year: "numeric",
	})
}

function formatCurrency(amount) {
	return new Intl.NumberFormat(DEFAULT_LOCALE, {
		style: "currency",
		currency: props.currency,
	}).format(amount || 0)
}

function getStatusTheme(status) {
	switch (status) {
		case "Active":
			return "green"
		case "Expired":
			return "red"
		case "Not Started":
			return "orange"
		case "Exhausted":
			return "gray"
		case "Disabled":
			return "red"
		default:
			return "gray"
	}
}

function parseErrorMessage(error) {
	try {
		if (error._server_messages) {
			const messages = JSON.parse(error._server_messages)
			if (Array.isArray(messages) && messages.length > 0) {
				const firstMessage = typeof messages[0] === "string" ? JSON.parse(messages[0]) : messages[0]
				return firstMessage.message || error.message || __("An error occurred")
			}
		}
		return error.message || __("An error occurred")
	} catch (e) {
		return error.message || __("An error occurred")
	}
}

function handleError(error, defaultMessage = __("An error occurred")) {
	const errorMessage = parseErrorMessage(error)
	showError(errorMessage || defaultMessage)
}

// Expose methods for parent component
defineExpose({
	loadCoupons,
})
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
	transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
	opacity: 0;
}
</style>
