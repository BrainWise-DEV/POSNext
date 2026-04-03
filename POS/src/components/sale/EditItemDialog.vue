<template>
	<!-- Custom Modal matching frappe-ui Dialog styling -->
	<!-- Uses @click.self pattern to properly handle teleported SelectInput dropdowns -->
	<Teleport to="body">
		<Transition name="dialog">
			<div
				v-if="show"
				class="fixed inset-0 bg-black/20 dark:bg-black/70 overflow-y-auto dialog-overlay outline-none z-dialog-overlay"
				@click.self="cancel"
			>
				<div class="flex min-h-screen flex-col items-center justify-center px-4 py-4 text-center">
					<Transition name="dialog-content">
						<div
							v-if="show"
							class="my-8 inline-block w-full max-w-md transform overflow-hidden rounded-xl bg-white text-left align-middle shadow-xl dialog-content z-dialog-content"
						>
							<!-- Header - matching frappe-ui Dialog style -->
							<div class="bg-white px-4 pb-6 pt-5 sm:px-6">
								<div class="flex">
									<div class="w-full flex-1">
										<div class="mb-6 flex items-center justify-between">
											<div class="flex items-center space-x-2">
												<h3 class="text-2xl font-semibold leading-6 text-gray-900">
													{{ __('Edit Item Details') }}
												</h3>
											</div>
											<button
												type="button"
												@click="cancel"
												class="rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
											>
												<FeatherIcon name="x" class="h-4 w-4" />
											</button>
										</div>

										<!-- Body Content -->
										<div v-if="localItem" class="flex flex-col gap-4">
											<!-- Item Header -->
											<div class="flex items-center gap-3 pb-4 border-b border-gray-200">
												<!-- Item Image -->
												<div class="w-16 h-16 bg-gray-100 rounded-lg flex-shrink-0 flex items-center justify-center overflow-hidden">
													<img
														v-if="localItem.image"
														:src="localItem.image"
														:alt="localItem.item_name"
														class="w-full h-full object-cover"
													/>
													<svg
														v-else
														class="h-8 w-8 text-gray-400"
														fill="none"
														stroke="currentColor"
														viewBox="0 0 24 24"
													>
														<path
															stroke-linecap="round"
															stroke-linejoin="round"
															stroke-width="2"
															d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
														/>
													</svg>
												</div>
												<!-- Item Info -->
												<div class="flex-1 min-w-0">
													<h3 class="text-base font-semibold text-gray-900 truncate">
														{{ localItem.item_name }}
													</h3>
													<p class="text-sm text-gray-500 truncate">
														{{ formatCurrency(localRate || localItem.price_list_rate || localItem.rate) }} / {{ selectedUomDisplayLabel || localUom || localItem.stock_uom || __('Nos', null, 'UOM') }}
													</p>
												</div>
											</div>

											<!-- Two Column Layout for Quantity, UOM, Rate, Warehouse -->
											<div class="grid grid-cols-2 gap-4">
												<!-- Left Column: Quantity and Rate -->
												<div class="flex flex-col gap-4">
													<!-- Quantity Control -->
													<div>
														<label class="block text-sm font-medium text-gray-700 mb-2 text-start">
                              {{ __('Quantity') }}
                            </label>
														<!-- For serial items, quantity is read-only (controlled by serial list) -->
														<div v-if="localItem?.has_serial_no && localSerials.length > 0" class="w-full h-7 border border-gray-300 rounded-lg bg-gray-50 flex items-center justify-center">
															<span class="text-sm font-semibold text-gray-600">{{ localSerials.length }}</span>
														</div>
														<!-- For non-serial items, show quantity controls -->
														<div v-else class="w-full h-7 border border-gray-300 rounded-lg bg-white flex items-center overflow-hidden">
															<button
																type="button"
																@click="decrementQuantity"
																class="w-7 h-7 min-w-7 bg-gray-100 hover:bg-gray-200 active:bg-gray-300 text-gray-700 font-bold text-base transition-colors flex items-center justify-center border-e border-gray-300"
															>
																−
															</button>
															<div class="flex-1 h-full flex items-center justify-center px-2">
																<input
																	v-model.number="localQuantity"
																	type="number"
																	min="0.0001"
																	step="any"
																	inputmode="decimal"
																	class="w-full text-center border-0 text-sm font-semibold focus:outline-none focus:ring-0 bg-transparent"
																	@input="handleQuantityInput"
																	@blur="handleQuantityBlur"
																	@keydown.enter="$event.target.blur()"
																/>
															</div>
															<button
																type="button"
																@click="incrementQuantity"
																class="w-7 h-7 min-w-7 bg-gray-100 hover:bg-gray-200 active:bg-gray-300 text-gray-700 font-bold text-base transition-colors flex items-center justify-center border-s border-gray-300"
															>
																+
															</button>
														</div>
													</div>

													<!-- Rate -->
													<div>
														<label class="block text-sm font-medium text-gray-700 mb-2 text-start">{{ __('Rate') }}</label>
														<div class="relative h-7">
															<span class="absolute inset-y-0 start-0 ps-3 flex items-center text-gray-500 text-sm font-medium">
																{{ currencySymbol }}
															</span>
															<input
																v-model.number="localRate"
																type="number"
																min="0"
																step="0.01"
																:readonly="!canEditRate"
																:class="canEditRate ? 'bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent' : 'bg-gray-50 cursor-not-allowed'"
																class="w-full h-7 border border-gray-300 rounded-lg ps-12 pe-3 text-sm font-semibold"
																:title="rateEditDisabledReason"
																@input="calculateTotals"
															/>
														</div>
														<!-- Compact warning when rate editing disabled due to pricing rules -->
														<p v-if="hasPricingRules && settingsStore.allowUserToEditRate" class="mt-1 text-xs text-amber-600 flex items-center gap-1">
															<FeatherIcon name="lock" class="w-3 h-3" />
															{{ __('Locked (offer applied)') }}
														</p>
													</div>
												</div>

												<!-- Right Column: UOM and Warehouse -->
												<div class="flex flex-col gap-4">
													<!-- UOM Selector -->
													<div>
														<label class="block text-sm font-medium text-gray-700 mb-2 text-start">
                              {{ __('UOM') }}
                              <span v-if="uomIsLocked" class="ms-1 text-xs text-amber-600">({{ __('Locked') }})</span>
                            </label>
                            <div v-if="uomIsLocked" class="w-full h-10 border border-amber-300 rounded-lg bg-amber-50 flex items-center justify-center">
                              <span class="text-sm font-semibold text-amber-700">{{ selectedUomDisplayLabel || localUom }}</span>
                            </div>
                            <SelectInput v-else v-model="localUom" :options="uomOptions" />
                            <p v-if="uomLockMessage" class="mt-1 text-xs text-amber-600 flex items-center gap-1">
                              <FeatherIcon name="lock" class="w-3 h-3" />
                              {{ uomLockMessage }}
                            </p>
													</div>

													<!-- Warehouse Selector -->
													<div>
														<label class="block text-sm font-medium text-gray-700 mb-2 text-start">{{ __('Warehouse') }}</label>
														<SelectInput v-model="localWarehouse" :options="warehouseOptions" @change="handleWarehouseChange" />
													</div>
												</div>
											</div>

											<!-- Serial Numbers Section (only for serial items) -->
											<div v-if="localItem?.has_serial_no && localSerials.length > 0" class="border-t border-gray-200 pt-4">
												<div class="flex items-center justify-between mb-3">
													<label class="block text-sm font-medium text-gray-700 text-start">
														{{ __('Serial Numbers') }}
														<span class="ms-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
															{{ localSerials.length }}
														</span>
													</label>
												</div>
												<div class="flex flex-col gap-2 max-h-40 overflow-y-auto">
													<div
														v-for="(serial, index) in localSerials"
														:key="serial"
														class="flex items-center justify-between gap-2 p-2 bg-gray-50 rounded-lg"
													>
														<div class="flex items-center gap-2">
															<span class="inline-flex items-center justify-center w-5 h-5 rounded-full bg-blue-600 text-white text-xs font-medium">
																{{ index + 1 }}
															</span>
															<span class="text-sm font-medium text-gray-900">{{ serial }}</span>
														</div>
														<button
															type="button"
															@click="removeSerial(serial)"
															:disabled="localSerials.length <= 1"
															class="p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
															:title="localSerials.length <= 1 ? __('Cannot remove last serial') : __('Remove serial')"
														>
															<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
																<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
															</svg>
														</button>
													</div>
												</div>
											</div>

											<!-- Item Discount Section (only if allowed by POS Profile) -->
											<div v-if="settingsStore.allowItemDiscount" class="border-t border-gray-200 pt-4">
												<label class="block text-sm font-medium text-gray-700 mb-3 text-start">{{ __('Item Discount') }}</label>
												<div v-if="effectiveItemDiscountWarning" class="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
													<div class="flex items-start gap-2">
														<FeatherIcon name="alert-triangle" class="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
														<div>{{ effectiveItemDiscountWarning }}</div>
													</div>
												</div>
												<div class="grid grid-cols-2 gap-3">
													<div>
														<label class="block text-xs text-gray-600 mb-1 text-start">{{ __('Discount Type') }}</label>
														<div v-if="!canEditItemDiscount" class="w-full h-10 border border-gray-200 rounded-lg bg-gray-100 flex items-center px-3 text-sm text-gray-500">
															{{ discountType === 'percentage' ? __('Percentage (%)') : __('Amount') }}
														</div>
														<SelectInput v-else v-model="discountType" :options="discountTypeOptions" @change="handleDiscountTypeChange" />
													</div>
													<div>
														<label class="block text-xs text-gray-600 mb-1 text-start">{{ discountType === 'percentage' ? __('Percentage') : __('Amount') }}</label>
														<div class="relative">
															<input
																v-model.number="discountValue"
																type="number"
																min="0"
																:max="discountType === 'percentage' ? 100 : undefined"
																step="0.01"
																:disabled="!canEditItemDiscount"
																:class="['w-full h-7 border rounded-lg px-3 pe-8 text-sm', canEditItemDiscount ? 'border-gray-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent' : 'border-gray-200 bg-gray-100 text-gray-500 cursor-not-allowed']"
																@input="calculateDiscount"
															/>
															<span :class="['absolute inset-y-0 end-0 pe-3 flex items-center text-sm', canEditItemDiscount ? 'text-gray-500' : 'text-gray-400']">
																{{ discountType === 'percentage' ? '%' : '' }}
															</span>
														</div>
													</div>
												</div>
												<p v-if="canEditItemDiscount && effectiveMaxDiscountPercent > 0" class="mt-2 text-xs text-gray-600">{{ __('Maximum allowed discount: {0}%', [effectiveMaxDiscountPercent]) }}<span v-if="effectiveMaxDiscountAmount > 0"> ({{ __('Up to {0}', [formatCurrency(effectiveMaxDiscountAmount)]) }})</span></p>
											</div>

											<!-- Totals -->
											<div class="bg-gray-50 rounded-lg p-4 flex flex-col gap-2">
												<div class="flex items-center justify-between text-sm">
													<span class="text-gray-600">{{ __('Subtotal:') }}</span>
													<span class="font-semibold text-gray-900">{{ formatCurrency(calculatedSubtotal) }}</span>
												</div>
												<div v-if="calculatedDiscount > 0" class="flex items-center justify-between text-sm text-red-600">
													<span>{{ __('Discount:') }}</span>
													<span class="font-semibold">-{{ formatCurrency(calculatedDiscount) }}</span>
												</div>
												<div class="flex items-center justify-between pt-2 border-t border-gray-200">
													<span class="text-base font-bold text-gray-900">{{ __('Total:') }}</span>
													<span class="text-lg font-bold text-blue-600">{{ formatCurrency(calculatedTotal) }}</span>
												</div>
											</div>

											<div
												v-if="stockDisplayPanel"
												class="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-700"
											>
												<div class="font-semibold mb-1">{{ stockDisplayPanel.title }}</div>
												<div>{{ __('Available: {0} {1}', [formatStockNumber(stockDisplayPanel.available), stockDisplayPanel.stockUom]) }}</div>
												<div>{{ __('Required: {0} {1}', [formatStockNumber(stockDisplayPanel.required), stockDisplayPanel.stockUom]) }}</div>
												<div v-if="stockDisplayPanel.allowNegative" class="mt-1">
													{{ __('Selling allowed (negative stock enabled)') }}
												</div>
											</div>
										</div>
									</div>
								</div>
							</div>

							<!-- Actions - matching frappe-ui Dialog style -->
							<div class="px-4 pb-7 pt-4 sm:px-6">
								<div class="flex items-center justify-end gap-2">
									<Button variant="subtle" @click="cancel">{{ __('Cancel') }}</Button>
									<Button
										variant="solid"
										@click="updateItem"
										:disabled="isUpdateDisabled"
									>
										<span v-if="isCheckingStock">{{ __('Checking Stock...') }}</span>
										<span v-else-if="!hasStock">{{ __('No Stock Available') }}</span>
										<span v-else>{{ __('Update Item') }}</span>
									</Button>
								</div>
							</div>
						</div>
					</Transition>
				</div>
			</div>
		</Transition>
	</Teleport>
</template>

<script setup>
import { useToast } from "@/composables/useToast"
import { usePOSSettingsStore } from "@/stores/posSettings"
import { getItemDiscountPolicy, getDiscountPolicyMessage, applyDiscountPolicy } from "@/utils/pos_connector/discountPolicy"
import { useSerialNumberStore } from "@/stores/serialNumber"
import { getItemStock } from "@/utils/stockValidator"
import { formatCurrency as formatCurrencyUtil, getCurrencySymbol, roundCurrency } from "@/utils/currency"
import { Button, FeatherIcon, createResource } from "frappe-ui"
import { computed, ref, watch } from "vue"
import SelectInput from "@/components/common/SelectInput.vue"

const { showSuccess, showError, showWarning } = useToast()
const settingsStore = usePOSSettingsStore()
const serialStore = useSerialNumberStore()

const props = defineProps({
	modelValue: Boolean,
	item: Object,
	warehouses: {
		type: Array,
		default: () => [],
	},
	currency: {
		type: String,
		default: "EGP",
	},
})

const emit = defineEmits(["update:modelValue", "update-item"])

// Local state
const localItem = ref(null)
const localQuantity = ref(1)
const localUom = ref("")
const localRate = ref(0)
const localWarehouse = ref("")
const discountType = ref("percentage")
const discountValue = ref(0)
const calculatedSubtotal = ref(0)
const calculatedDiscount = ref(0)
const calculatedTotal = ref(0)
const hasStock = ref(true)
const isCheckingStock = ref(false)
const isInitializingItem = ref(false)
const uomRateRequestId = ref(0)
const localSerials = ref([]) // List of serial numbers for this item
const removedSerials = ref([]) // Track serials removed during this edit session
const originalSerials = ref([]) // Original serials when dialog opened
const originalPriceListRate = ref(0) // Original price_list_rate when dialog opened (for rate edit validation)

function getSnapshotUom(item) {
	return item?.selected_uom || item?.uom || item?.stock_uom || __("Nos", null, "UOM")
}

function getSnapshotRate(item) {
	return Number(
		item?.selected_display_rate ??
		item?.rate ??
		item?.price_list_rate ??
		0
	) || 0
}

function getSnapshotQuantity(item) {
	return Number(
		item?.selected_qty ??
		item?.quantity ??
		1
	) || 1
}

function getSnapshotPriceListRate(item) {
	return Number(
		item?.price_list_rate ??
		item?.selected_display_rate ??
		item?.rate ??
		0
	) || 0
}

function normalizeWarehouseValue(value) {
	if (!value) return ""
	if (typeof value === "string") return value
	if (typeof value === "object") {
		return value.value || value.name || value.label || value.warehouse || ""
	}
	return ""
}

const getItemDetailsResource = createResource({
	url: "pos_next.api.items.get_item_details",
	auto: false,
})

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit("update:modelValue", val),
})

const availableUoms = computed(() => {
	if (!localItem.value || !localItem.value.item_uoms) return []
	return localItem.value.item_uoms.filter(
		(u) => u.uom !== localItem.value.stock_uom,
	)
})

const currencySymbol = computed(() => getCurrencySymbol(props.currency))

const allowNegativeStock = computed(() => Boolean(settingsStore?.settings?.allow_negative_stock))

const isUpdateDisabled = computed(() => {
	if (isCheckingStock.value) return true
	if (allowNegativeStock.value) return false
	return !hasStock.value
})

const updateButtonLabel = computed(() => {
	if (isCheckingStock.value) return __('Checking Stock...')
	if (allowNegativeStock.value) return __('Update Item')
	if (!hasStock.value) return __('No Stock Available')
	return __('Update Item')
})

// Check if item has pricing rules applied (promotional offers)
const hasPricingRules = computed(() => {
	if (!localItem.value) return false
	return Boolean(localItem.value.pricing_rules) && localItem.value.pricing_rules.length > 0
})

// Rate editing is allowed only if:
// 1. POS Settings allows rate editing AND
// 2. Item does NOT have pricing rules (promotional offers) applied
const canEditRate = computed(() => {
	return settingsStore.allowUserToEditRate && !hasPricingRules.value
})

// Tooltip message for why rate editing is disabled
const rateEditDisabledReason = computed(() => {
	if (!settingsStore.allowUserToEditRate) {
		return __('Rate editing is disabled')
	}
	if (hasPricingRules.value) {
		return __('Locked (offer applied)')
	}
	return ''
})

// Options for SelectInput components
const uomOptions = computed(() => {
	if (!localItem.value) return []
	const allowedSet = new Set(getAllowedSellUoms(localItem.value || {}))
	const options = []
	const seen = new Set()
	const pushOption = (uom, conversionFactor = 1) => {
		if (!uom || seen.has(uom)) return
		if (allowedSet.size > 0 && !allowedSet.has(uom)) return
		seen.add(uom)
		options.push({
			value: uom,
			label: Number(conversionFactor || 1) > 1 ? `${uom} x ${Number(conversionFactor || 1)}` : uom,
		})
	}
	pushOption(localItem.value.stock_uom, 1)
	if (availableUoms.value.length > 0) availableUoms.value.forEach((uomData) => pushOption(uomData.uom, uomData.conversion_factor || 1))
	if (!seen.has(localUom.value) && localUom.value && isUomAllowed(localItem.value, localUom.value)) pushOption(localUom.value, getConversionFactorForUom(localUom.value))
	return options
})

const warehouseOptions = computed(() => {
	if (props.warehouses.length > 0) {
		return props.warehouses.map(w => ({
			value: w.name,
			label: w.warehouse || w.name
		}))
	}
	return [{ value: localWarehouse.value, label: localWarehouse.value || __('Default') }]
})
const effectiveRateDiscountPercent = computed(() => {
	if (!canEditItemDiscount.value) return 0
	return effectiveMaxDiscountPercent.value
})

const discountTypeOptions = computed(() => [
	{ value: 'percentage', label: __('Percentage (%)') },
	{ value: 'amount', label: __('Amount') }
])

function normalizePolicyUomRows(rows = []) {
	if (!Array.isArray(rows)) return []
	return rows.map((row) => {
		if (typeof row === 'string') return { uom: row, allow_for_selling: true }
		const uom = row?.uom || row?.value || row?.name || null
		if (!uom) return null
		return { uom, allow_for_selling: row?.allow_for_selling }
	}).filter(Boolean)
}

function getItemUomPolicy(item) {
	return item?.uom_policy || item?._uom_policy || {}
}

function getAllowedSellUoms(item) {
	const explicit = []
	if (Array.isArray(item?.allowed_uoms)) explicit.push(...item.allowed_uoms)
	if (Array.isArray(item?.sellable_uoms)) explicit.push(...item.sellable_uoms)
	if (Array.isArray(item?.allowed_sell_uoms)) explicit.push(...item.allowed_sell_uoms)
	const normalizedExplicit = normalizePolicyUomRows(explicit)
	if (normalizedExplicit.length > 0) return [...new Set(normalizedExplicit.map((row) => row.uom).filter(Boolean))]
	const policy = getItemUomPolicy(item)
	const normalizedAllowed = normalizePolicyUomRows(policy?.allowed_uoms)
	if (normalizedAllowed.length > 0) return [...new Set(normalizedAllowed.map((row) => row.uom).filter(Boolean))]
	const normalizedAll = normalizePolicyUomRows(policy?.all_uoms)
	if (normalizedAll.length > 0) return [...new Set(normalizedAll.filter((row) => row.allow_for_selling !== false).map((row) => row.uom).filter(Boolean))]
	return []
}

function isUomAllowed(item, uom) {
	if (!item || !uom) return false
	if (item?.is_resolved_barcode) return uom === (item?.selected_uom || item?.uom || item?.stock_uom)
	const allowed = getAllowedSellUoms(item)
	if (allowed.length > 0) return allowed.includes(uom)
	return true
}

const itemDiscountPolicy = computed(() => getItemDiscountPolicy(localItem.value || {}))
const settingsMaxDiscountPercent = computed(() => {
	const raw = Number(settingsStore.maxDiscountAllowed ?? settingsStore?.settings?.max_discount ?? 0)
	return Number.isFinite(raw) && raw > 0 ? raw : 0
})
const itemMaxDiscountPercent = computed(() => {
	const raw = Number(itemDiscountPolicy.value?.max_discount || 0)
	return Number.isFinite(raw) && raw > 0 ? raw : 0
})
const effectiveMaxDiscountPercent = computed(() => {
	const values = [settingsMaxDiscountPercent.value, itemMaxDiscountPercent.value].filter((v) => v > 0)
	if (!values.length) return 0
	return Math.min(...values)
})
const directDiscountAllowed = computed(() => {
	const raw = localItem.value?.discount_allowed
	if (raw === 0 || raw === "0" || raw === false) return false
	if (raw === 1 || raw === "1" || raw === true) return true
	return null
})

const canEditItemDiscount = computed(() => {
	if (directDiscountAllowed.value !== null) {
		return directDiscountAllowed.value
	}
	return Boolean(itemDiscountPolicy.value?.discount_allowed)
})
const itemDiscountWarning = computed(() => getDiscountPolicyMessage(itemDiscountPolicy.value))
const effectiveItemDiscountWarning = computed(() => {
	if (!canEditItemDiscount.value) {
		if (directDiscountAllowed.value === false) {
			return __('Item has no discount allowed')
		}
		return itemDiscountWarning.value || __('Discount is not allowed for this item')
	}
	if (effectiveMaxDiscountPercent.value > 0) {
		return __('Maximum allowed discount is {0}%', [effectiveMaxDiscountPercent.value])
	}
	return ''
})
const effectiveMaxDiscountAmount = computed(() => {
	if (effectiveMaxDiscountPercent.value <= 0 || calculatedSubtotal.value <= 0) return 0
	return roundCurrency((calculatedSubtotal.value * effectiveMaxDiscountPercent.value) / 100)
})
const uomIsLocked = computed(() => {
	if (!localItem.value) return true
	if (localItem.value?.is_resolved_barcode) return true
	return uomOptions.value.length <= 1
})
const uomLockMessage = computed(() => {
	if (!localItem.value) return ''
	if (localItem.value?.is_resolved_barcode) return __('UOM is locked for barcode-resolved item')
	if (uomOptions.value.length <= 1) return __('Only allowed sell UOM can be used for this item')
	return ''
})


const selectedUomDisplayLabel = computed(() => {
	if (!localItem.value) return localUom.value || ""

	const conversionFactor = Number(
		localItem.value?.selected_conversion_factor ??
		localItem.value?.conversion_factor ??
		getConversionFactorForUom(localUom.value) ??
		1
	) || 1

	return localItem.value?.selected_uom_label ||
		(conversionFactor > 1
			? `${localUom.value} x ${conversionFactor}`
			: localUom.value)
})

const stockDisplayPanel = computed(() => {
	if (!localItem.value) return null
	const stockUom = localItem.value?.selected_stock_uom || localItem.value?.stock_uom || localUom.value || ""
	const conversionFactor = Number(localItem.value?.selected_conversion_factor ?? localItem.value?.conversion_factor ?? getConversionFactorForUom(localUom.value) ?? 1) || 1
	const available = Number(localItem.value?.selected_stock_qty ?? localItem.value?.available_stock_qty ?? localItem.value?.actual_qty ?? localItem.value?.stock_qty ?? 0) || 0
	const required = Number(localQuantity.value || 0) * conversionFactor
	let message = __('Stock available for this quantity')
	if (required > available) {
		message = allowNegativeStock.value ? __('Selling allowed (negative stock enabled)') : __('Insufficient stock for this quantity')
	}
	return { title: __('Stock status'), available, required, stockUom, allowNegative: allowNegativeStock.value, message }
})

// Initialize local state when item changes
watch(
	() => props.item,
	(newItem) => {
		if (newItem) {
			isInitializingItem.value = true
			localItem.value = { ...newItem }
			localQuantity.value = getSnapshotQuantity(newItem)
			localUom.value = getSnapshotUom(newItem)
			localRate.value = getSnapshotRate(newItem)
			originalPriceListRate.value = getSnapshotPriceListRate(newItem)
			localWarehouse.value = normalizeWarehouseValue(
				newItem.warehouse || props.warehouses[0]?.name || ""
			)

			// Initialize serial numbers
			if (newItem.has_serial_no && newItem.serial_no) {
				const serials = newItem.serial_no.split('\n').filter(s => s.trim())
				localSerials.value = [...serials]
				originalSerials.value = [...serials]
				removedSerials.value = []
				localQuantity.value = serials.length
			} else {
				localSerials.value = []
				originalSerials.value = []
				removedSerials.value = []
			}

			// Initialize discount
			if (newItem.discount_percentage && newItem.discount_percentage > 0) {
				discountType.value = "percentage"
				discountValue.value = newItem.discount_percentage
			} else if (newItem.discount_amount && newItem.discount_amount > 0) {
				discountType.value = "amount"
				discountValue.value = newItem.discount_amount
			} else {
				discountType.value = "percentage"
				discountValue.value = 0
			}

			// Force reset when item itself says discount is not allowed
			if (
				newItem.discount_allowed === 0 ||
				newItem.discount_allowed === "0" ||
				newItem.discount_allowed === false
			) {
				discountType.value = "percentage"
				discountValue.value = 0
			}

			// Reset stock check state
			hasStock.value = true
			isCheckingStock.value = false

			calculateTotals()
			isInitializingItem.value = false
		}
	},
	{ immediate: true },
)
watch(localUom, (newUom, oldUom) => {
	if (!newUom || newUom === oldUom || isInitializingItem.value) return
	if (!isUomAllowed(localItem.value, newUom)) {
		localUom.value = oldUom || localItem.value?.stock_uom || localItem.value?.uom || ''
		showWarning(__('UOM "{0}" is not allowed to sell for this item', [newUom]))
		return
	}
	handleUomChange(newUom)
})

/**
 * Intelligently determine the step size based on current quantity
 * - Whole numbers (1, 2, 3): step by 1
 * - Multiples of 0.5 (1.5, 2.5): step by 0.5
 * - Multiples of 0.25 (0.25, 0.75): step by 0.25
 * - Multiples of 0.1 (0.1, 0.3): step by 0.1
 * - Other decimals: step by 0.01
 */
function getSmartStep(quantity) {
	// Check if it's a whole number
	if (quantity === Math.floor(quantity)) {
		return 1
	}

	// Round to 4 decimal places to avoid floating point errors
	const rounded = Math.round(quantity * 10000) / 10000

	// Check if it's a multiple of 0.5
	if (Math.abs((rounded % 0.5)) < 0.0001) {
		return 0.5
	}

	// Check if it's a multiple of 0.25
	if (Math.abs((rounded % 0.25)) < 0.0001) {
		return 0.25
	}

	// Check if it's a multiple of 0.1
	if (Math.abs((rounded % 0.1)) < 0.0001) {
		return 0.1
	}

	// For other decimals, use 0.01 for fine control
	return 0.01
}

function incrementQuantity() {
	const step = getSmartStep(localQuantity.value)
	localQuantity.value = Math.round((localQuantity.value + step) * 10000) / 10000
	calculateTotals()
}

function decrementQuantity() {
	const step = getSmartStep(localQuantity.value)
	const newQty = Math.round((localQuantity.value - step) * 10000) / 10000

	if (newQty > 0) {
		localQuantity.value = newQty
		calculateTotals()
	}
}

function handleQuantityInput() {
	// Allow any value during typing, just recalculate totals
	// Don't validate or reset - let user type freely
	if (localQuantity.value > 0 && !isNaN(localQuantity.value)) {
		calculateTotals()
	}
}

function handleQuantityBlur() {
	// Validate and fix the quantity when user is done editing (leaves the field)
	if (!localQuantity.value || localQuantity.value <= 0 || isNaN(localQuantity.value)) {
		// If invalid, reset to 1
		localQuantity.value = 1
	} else {
		// Round to 4 decimal places for consistency
		localQuantity.value = Math.round(localQuantity.value * 10000) / 10000
	}
	calculateTotals()
}

function getConversionFactorForUom(uom) {
	if (!localItem.value) return 1
	if (uom === localItem.value.stock_uom) return 1
	const uomData = localItem.value.item_uoms?.find((itemUom) => itemUom.uom === uom)
	return uomData?.conversion_factor || 1
}

async function getRateForUom(uom) {
	if (!localItem.value) return 0

	// Primary source: fetch exact price_list_rate for selected UOM from backend.
	const posProfile = settingsStore.settings?.pos_profile || localItem.value.pos_profile
	if (localItem.value.item_code && posProfile) {
		try {
			const itemDetails = await getItemDetailsResource.submit({
				item_code: localItem.value.item_code,
				pos_profile: posProfile,
				qty: localQuantity.value || 1,
				uom,
			})
			const serverRate = Number(itemDetails?.price_list_rate ?? itemDetails?.rate)
			if (!isNaN(serverRate) && serverRate > 0) {
				return serverRate
			}
		} catch (error) {
			console.error("Error fetching UOM item price rate:", error)
		}
	}

	// Secondary source: preloaded UOM prices on item payload.
	if (localItem.value.uom_prices?.[uom] !== undefined) {
		return Number(localItem.value.uom_prices[uom]) || 0
	}

	// Final fallback: keep current known item rate (no conversion-based pricing).
	return Number(localItem.value.price_list_rate || localItem.value.rate || localRate.value || 0)
}

async function handleUomChange(newUom) {
	const selectedUom = newUom || localUom.value
	if (!localItem.value || !selectedUom) {
		calculateTotals()
		return
	}

	const requestId = ++uomRateRequestId.value
	const fetchedRate = await getRateForUom(selectedUom)
	// Ignore stale responses if user changes UOM repeatedly.
	if (requestId !== uomRateRequestId.value) return

	const newRate = roundCurrency(fetchedRate)
	const newConversionFactor = getConversionFactorForUom(selectedUom)

	// Keep local state consistent so update payload has correct UOM pricing metadata.
	localRate.value = newRate
	originalPriceListRate.value = newRate
	localItem.value.uom = selectedUom
	localItem.value.conversion_factor = newConversionFactor
	localItem.value.rate = newRate
	localItem.value.price_list_rate = newRate
	localItem.value.selected_uom = selectedUom
	localItem.value.selected_conversion_factor = newConversionFactor
	localItem.value.selected_uom_label =
		newConversionFactor > 1
			? `${selectedUom} x ${newConversionFactor}`
			: selectedUom
	localItem.value.selected_display_rate = newRate
	localItem.value.selected_stock_uom = localItem.value.stock_uom || selectedUom
	localItem.value.selected_stock_uom_qty_required = localQuantity.value * newConversionFactor

	calculateTotals()
}

async function handleWarehouseChange() {
	const selectedWarehouse = normalizeWarehouseValue(localWarehouse.value)
	if (!localItem.value || !selectedWarehouse) return

	localWarehouse.value = selectedWarehouse
	isCheckingStock.value = true
	try {
		const availableStock = await getItemStock(
			localItem.value.item_code,
			selectedWarehouse,
		)

		if (availableStock === 0) {
			hasStock.value = allowNegativeStock.value
			if (allowNegativeStock.value) {
				showWarning(
					__('"{0}" is not available in warehouse "{1}", but negative stock is allowed.', [
						localItem.value.item_name,
						selectedWarehouse,
					])
				)
			} else {
				showError(
					__('"{0}" is not available in warehouse "{1}". Please select another warehouse.', [
						localItem.value.item_name,
						selectedWarehouse,
					])
				)
			}
		} else if (availableStock < localQuantity.value) {
			hasStock.value = allowNegativeStock.value
			showWarning(
				__('Only {0} units of "{1}" available in "{2}". Current quantity: {3}', [
					availableStock,
					localItem.value.item_name,
					selectedWarehouse,
					localQuantity.value
				])
			)
		} else {
			hasStock.value = true
			showSuccess(
				__('{0} units available in "{1}"', [availableStock, selectedWarehouse])
			)
		}
	} catch (error) {
		console.error("Error checking warehouse stock:", error)
		hasStock.value = true
	} finally {
		isCheckingStock.value = false
	}
}

function sanitizeDiscountInput({ discount_percentage = 0, discount_amount = 0, subtotal = 0, item = null } = {}) {
	let sanitized = applyDiscountPolicy(item || localItem.value || {}, { discount_percentage, discount_amount }, { item: item || localItem.value || {}, subtotal })
	if (!canEditItemDiscount.value) return { discount_percentage: 0, discount_amount: 0 }
	if (effectiveMaxDiscountPercent.value > 0 && subtotal > 0) {
		const maxAmount = roundCurrency((subtotal * effectiveMaxDiscountPercent.value) / 100)
		if (Number(sanitized.discount_percentage || 0) > 0) {
			sanitized.discount_percentage = Math.min(Number(sanitized.discount_percentage || 0), effectiveMaxDiscountPercent.value)
			sanitized.discount_amount = 0
		} else if (Number(sanitized.discount_amount || 0) > 0) {
			sanitized.discount_amount = Math.min(roundCurrency(Number(sanitized.discount_amount || 0)), maxAmount)
			sanitized.discount_percentage = 0
		}
	}
	return { discount_percentage: roundCurrency(Number(sanitized.discount_percentage || 0)), discount_amount: roundCurrency(Number(sanitized.discount_amount || 0)) }
}

function handleDiscountTypeChange() {
	if (!canEditItemDiscount.value) {
		discountType.value = 'percentage'
		discountValue.value = 0
		calculateTotals()
		return
	}
	discountValue.value = 0
	calculateTotals()
}

function calculateDiscount() {
	if (!canEditItemDiscount.value) {
		discountType.value = 'percentage'
		discountValue.value = 0
		calculatedDiscount.value = 0
		calculatedTotal.value = roundCurrency(calculatedSubtotal.value)
		return
	}
	if (discountValue.value !== null && discountValue.value !== undefined && !isNaN(discountValue.value)) {
		discountValue.value = roundCurrency(discountValue.value)
	}
	const sanitized = sanitizeDiscountInput({ discount_percentage: discountType.value === 'percentage' ? discountValue.value : 0, discount_amount: discountType.value === 'amount' ? discountValue.value : 0, subtotal: calculatedSubtotal.value, item: localItem.value })
	if (discountType.value === 'percentage') {
		discountValue.value = sanitized.discount_percentage
		calculatedDiscount.value = roundCurrency((calculatedSubtotal.value * discountValue.value) / 100)
	} else {
		discountValue.value = sanitized.discount_amount
		calculatedDiscount.value = roundCurrency(discountValue.value)
	}
	calculatedTotal.value = roundCurrency(calculatedSubtotal.value - calculatedDiscount.value)
}

function calculateTotals() {
	calculatedSubtotal.value = localRate.value * localQuantity.value

	if (localItem.value) {
		const conversionFactor = Number(
			localItem.value?.selected_conversion_factor ??
			localItem.value?.conversion_factor ??
			getConversionFactorForUom(localUom.value) ??
			1
		) || 1

		localItem.value.selected_qty = localQuantity.value
		localItem.value.selected_display_rate = localRate.value
		localItem.value.selected_display_subtotal = calculatedSubtotal.value
		localItem.value.selected_stock_uom_qty_required = localQuantity.value * conversionFactor
	}

	calculateDiscount()
}

function removeSerial(serialNo) {
	// Remove from local list
	const index = localSerials.value.indexOf(serialNo)
	if (index > -1) {
		localSerials.value.splice(index, 1)
		// Track removed serial (will be returned to cache on confirm)
		removedSerials.value.push(serialNo)
		// Update quantity to match serial count
		localQuantity.value = localSerials.value.length
		calculateTotals()
	}
}
//stock number formatter
function formatStockNumber(value) {
	const num = Number(value)
	if (!Number.isFinite(num)) return "0"
	if (Math.abs(num - Math.round(num)) < 0.0001) {
		return String(Math.round(num))
	}
	return String(Math.round(num * 10000) / 10000)
}


function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}

function updateItem() {
	const selectedWarehouse = normalizeWarehouseValue(
		localWarehouse.value || localItem.value?.warehouse,
	)

	// Check if rate was manually edited
	const isRateManuallyEdited = localRate.value !== originalPriceListRate.value

	// ========================================================================
	// RATE EDIT VALIDATION
	// ========================================================================
	if (isRateManuallyEdited) {
		// Validate rate is positive
		if (localRate.value <= 0) {
			showError(__('Rate must be greater than zero'))
			return
		}

		// If item discount is not allowed, do not allow reducing rate below original
		if (!canEditItemDiscount.value && localRate.value < originalPriceListRate.value) {
			showError(__('Discount is not allowed for this item'))
			return
		}

		// Validate against stricter effective max discount if rate was reduced
		if (
			canEditItemDiscount.value &&
			effectiveRateDiscountPercent.value > 0 &&
			localRate.value < originalPriceListRate.value
		) {
			const discountPercent =
				((originalPriceListRate.value - localRate.value) / originalPriceListRate.value) * 100
			const roundedDiscount = Math.round(discountPercent * 100) / 100

			if (roundedDiscount > effectiveRateDiscountPercent.value) {
				showError(
					__('Rate reduction of {0}% exceeds maximum allowed discount of {1}%', [
						roundedDiscount.toFixed(2),
						effectiveRateDiscountPercent.value
					])
				)
				return
			}
		}
	}

	const conversionFactor = getConversionFactorForUom(localUom.value)
	const availableStockQty =
		localItem.value?.selected_stock_qty ??
		localItem.value?.available_stock_qty ??
		localItem.value?.actual_qty ??
		localItem.value?.stock_qty ??
		null

	if (!isUomAllowed(localItem.value, localUom.value)) {
		showError(__('UOM "{0}" is not allowed to sell for this item', [localUom.value]))
		return
	}

	const sanitizedDiscount = sanitizeDiscountInput({
		discount_percentage: discountType.value === "percentage" ? discountValue.value : 0,
		discount_amount: discountType.value === "amount" ? discountValue.value : 0,
		subtotal: localRate.value * localQuantity.value,
		item: localItem.value,
	})

	const updatedItem = {
		...localItem.value,
		quantity: localQuantity.value,
		uom: localUom.value,
		conversion_factor: conversionFactor,
		rate: localRate.value,
		price_list_rate: originalPriceListRate.value,
		warehouse: selectedWarehouse,
		selected_uom: localUom.value,
		selected_uom_label:
			conversionFactor > 1
				? `${localUom.value} x ${conversionFactor}`
				: localUom.value,
		selected_conversion_factor: conversionFactor,
		selected_stock_uom: localItem.value?.stock_uom || localUom.value,
		selected_qty: localQuantity.value,
		selected_display_rate: localRate.value,
		selected_display_subtotal: localRate.value * localQuantity.value,
		selected_stock_uom_qty_required: localQuantity.value * conversionFactor,
		selected_stock_qty: availableStockQty,
		discount_percentage: sanitizedDiscount.discount_percentage,
		discount_amount: sanitizedDiscount.discount_amount,
		// Track manual rate edits for audit logging
		is_rate_manually_edited: isRateManuallyEdited ? 1 : 0,
		original_rate: isRateManuallyEdited ? originalPriceListRate.value : null,
	}

	// Update serial numbers if item has serials
	if (localItem.value.has_serial_no) {
		updatedItem.serial_no = localSerials.value.join('\n')
		updatedItem.quantity = localSerials.value.length

		// Return removed serials to cache now that update is confirmed
		if (removedSerials.value.length > 0) {
			serialStore.returnSerials(localItem.value.item_code, removedSerials.value)
		}
	}

	emit("update-item", updatedItem)
	show.value = false
}

function cancel() {
	show.value = false
}
</script>

<style scoped>
/* Hide number input spinners */
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
	appearance: none;
	-webkit-appearance: none;
	margin: 0;
}

input[type="number"] {
	appearance: textfield;
	-moz-appearance: textfield;
}

/* Use CSS custom properties from index.css for consistent z-index layering */
.z-dialog-overlay {
	z-index: var(--z-dialog-overlay, 400);
}

.z-dialog-content {
	z-index: var(--z-dialog-content, 500);
}
</style>
