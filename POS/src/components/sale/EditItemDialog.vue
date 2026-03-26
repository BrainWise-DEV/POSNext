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
														{{ formatCurrency(localRate) }} / {{ localUom || localItem.stock_uom || __('Nos', null, 'UOM') }}
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
															<span v-if="localItem?.is_resolved_barcode" class="ms-1 text-xs text-amber-600">({{ __('Locked') }})</span>
														</label>
														<!-- For serial items, quantity is read-only (controlled by serial list) -->
														<div v-if="localItem?.has_serial_no && localSerials.length > 0" class="w-full h-7 border border-gray-300 rounded-lg bg-gray-50 flex items-center justify-center">
															<span class="text-sm font-semibold text-gray-600">{{ localSerials.length }}</span>
														</div>
														<!-- For resolved barcode items, quantity is read-only -->
														<div v-else-if="localItem?.is_resolved_barcode" class="w-full h-10 border border-amber-300 rounded-lg bg-amber-50 flex items-center justify-center">
															<span class="text-sm font-semibold text-amber-700">{{ localQuantity }}</span>
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
															<span v-if="localItem?.is_resolved_barcode" class="ms-1 text-xs text-amber-600">({{ __('Locked') }})</span>
														</label>
														<div v-if="localItem?.is_resolved_barcode" class="w-full h-10 border border-amber-300 rounded-lg bg-amber-50 flex items-center justify-center">
															<span class="text-sm font-semibold text-amber-700">{{ localUom }}</span>
														</div>
														<SelectInput v-else v-model="localUom" :options="uomOptions" @change="handleUomChange" />
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
												<div class="grid grid-cols-2 gap-3">
													<div>
														<label class="block text-xs text-gray-600 mb-1 text-start">{{ __('Discount Type') }}</label>
														<SelectInput v-model="discountType" :options="discountTypeOptions" @change="handleDiscountTypeChange" />
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
																class="w-full h-7 border border-gray-300 rounded-lg px-3 pe-8 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
																@input="calculateDiscount"
															/>
															<span class="absolute inset-y-0 end-0 pe-3 flex items-center text-gray-500 text-sm">
																{{ discountType === 'percentage' ? '%' : '' }}
															</span>
														</div>
													</div>
												</div>
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
										:disabled="!hasStock || isCheckingStock"
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
import { useInvoice } from "@/composables/useInvoice"
import uomPolicyAdapter from "@/utils/uom_policy_adapter"
import { useToast } from "@/composables/useToast"
import { usePOSSettingsStore } from "@/stores/posSettings"
import { useSerialNumberStore } from "@/stores/serialNumber"
import { getItemStock } from "@/utils/stockValidator"
import { formatCurrency as formatCurrencyUtil, getCurrencySymbol, roundCurrency } from "@/utils/currency"
import { Button, FeatherIcon } from "frappe-ui"
import { computed, ref, watch } from "vue"
import SelectInput from "@/components/common/SelectInput.vue"

const { showSuccess, showError, showWarning } = useToast()
const settingsStore = usePOSSettingsStore()
const serialStore = useSerialNumberStore()
const { resolveUomPricing } = useInvoice()

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
const localSerials = ref([])
const removedSerials = ref([])
const originalSerials = ref([])
const originalPriceListRate = ref(0)

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit("update:modelValue", val),
})

const availableUoms = computed(() => {
	if (!localItem.value) return []
	return uomPolicyAdapter
		.filterAllowedItemUoms(localItem.value)
		.filter((u) => u.uom !== localItem.value.stock_uom)
})

const selectableUoms = computed(() => {
	if (!localItem.value) return []
	return uomPolicyAdapter.buildSelectableUoms(localItem.value)
})

const isUomLocked = computed(() => {
	if (!localItem.value) return true
	if (localItem.value.is_resolved_barcode) return true
	return uomPolicyAdapter.isUomLocked(localItem.value)
})

const currencySymbol = computed(() => getCurrencySymbol(props.currency))

const hasPricingRules = computed(() => {
	if (!localItem.value) return false
	return Boolean(localItem.value.pricing_rules) && localItem.value.pricing_rules.length > 0
})

const canEditRate = computed(() => {
	return settingsStore.allowUserToEditRate && !hasPricingRules.value
})

const rateEditDisabledReason = computed(() => {
	if (!settingsStore.allowUserToEditRate) {
		return __('Rate editing is disabled')
	}
	if (hasPricingRules.value) {
		return __('Locked (offer applied)')
	}
	return ""
})

const uomOptions = computed(() => {
	if (!localItem.value) return []
	return selectableUoms.value.map((uomData) => ({
		value: uomData.uom,
		label: uomData.uom,
	}))
})

const warehouseOptions = computed(() => {
	if (props.warehouses.length > 0) {
		return props.warehouses.map((w) => ({
			value: w.name,
			label: w.warehouse || w.name,
		}))
	}
	return [{ value: localWarehouse.value, label: localWarehouse.value || __('Default') }]
})

const discountTypeOptions = computed(() => [
	{ value: "percentage", label: __('Percentage (%)') },
	{ value: "amount", label: __('Amount') },
])

watch(
	() => props.item,
	async (newItem) => {
		if (newItem) {
			await uomPolicyAdapter.ensurePolicyLoaded(newItem)
			const normalizedItem = await uomPolicyAdapter.normalizeItemAsync({ ...newItem })

			localItem.value = normalizedItem
			localQuantity.value = normalizedItem.quantity || 1
			localUom.value = normalizedItem.uom || normalizedItem.stock_uom || __("Nos")
			localRate.value = normalizedItem.rate || 0
			originalPriceListRate.value =
				normalizedItem.price_list_rate || normalizedItem.rate || 0
			localWarehouse.value =
				normalizedItem.warehouse || props.warehouses[0]?.name || ""

			if (normalizedItem.has_serial_no && normalizedItem.serial_no) {
				const serials = normalizedItem.serial_no.split("\n").filter((s) => s.trim())
				localSerials.value = [...serials]
				originalSerials.value = [...serials]
				removedSerials.value = []
				localQuantity.value = serials.length
			} else {
				localSerials.value = []
				originalSerials.value = []
				removedSerials.value = []
			}

			if (
				normalizedItem.discount_percentage &&
				normalizedItem.discount_percentage > 0
			) {
				discountType.value = "percentage"
				discountValue.value = normalizedItem.discount_percentage
			} else if (
				normalizedItem.discount_amount &&
				normalizedItem.discount_amount > 0
			) {
				discountType.value = "amount"
				discountValue.value = normalizedItem.discount_amount
			} else {
				discountType.value = "percentage"
				discountValue.value = 0
			}

			hasStock.value = true
			isCheckingStock.value = false

			calculateTotals()
		}
	},
	{ immediate: true },
)

function getSmartStep(quantity) {
	if (quantity === Math.floor(quantity)) {
		return 1
	}

	const rounded = Math.round(quantity * 10000) / 10000

	if (Math.abs(rounded % 0.5) < 0.0001) {
		return 0.5
	}

	if (Math.abs(rounded % 0.25) < 0.0001) {
		return 0.25
	}

	if (Math.abs(rounded % 0.1) < 0.0001) {
		return 0.1
	}

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
	if (localQuantity.value > 0 && !isNaN(localQuantity.value)) {
		calculateTotals()
	}
}

function handleQuantityBlur() {
	if (!localQuantity.value || localQuantity.value <= 0 || isNaN(localQuantity.value)) {
		localQuantity.value = 1
	} else {
		localQuantity.value = Math.round(localQuantity.value * 10000) / 10000
	}
	calculateTotals()
}

async function handleUomChange() {
	if (!localItem.value || !localUom.value) {
		calculateTotals()
		return
	}

	const applied = uomPolicyAdapter.applySelectedUom(
		localItem.value,
		localUom.value,
	)

	if (!applied.ok) {
		const safeUom = applied.safe_uom || uomPolicyAdapter.getDefaultUom(localItem.value)
		localUom.value = safeUom
		localItem.value = uomPolicyAdapter.applySafeDefaultUom(localItem.value)

		showError(
			__('UOM "{0}" is not allowed for item "{1}".', [
				localUom.value,
				localItem.value.item_name || localItem.value.item_code,
			]),
		)
		calculateTotals()
		return
	}

	try {
		localItem.value = applied.item

		const uomRow = uomPolicyAdapter.getUomRow(localItem.value, localUom.value)
		const conversionFactor = uomRow?.conversion_factor || 1

		const pricing = await resolveUomPricing(
			localItem.value,
			localUom.value,
			conversionFactor,
			localQuantity.value || 1,
		)

		localRate.value = pricing.rate || pricing.price_list_rate || 0
		originalPriceListRate.value = pricing.price_list_rate || localRate.value

		localItem.value = {
			...localItem.value,
			uom: localUom.value,
			conversion_factor: conversionFactor,
			rate: localRate.value,
			price_list_rate: originalPriceListRate.value,
		}

		calculateTotals()
	} catch (err) {
		console.error("UOM pricing refresh failed:", err)
		calculateTotals()
	}
}


async function handleWarehouseChange() {
	if (!localItem.value || !localWarehouse.value) return

	isCheckingStock.value = true
	try {
		const availableStock = await getItemStock(
			localItem.value.item_code,
			localWarehouse.value,
		)

		if (availableStock === 0) {
			hasStock.value = false
			showError(
				__('"{0}" is not available in warehouse "{1}". Please select another warehouse.', [
					localItem.value.item_name,
					localWarehouse.value,
				]),
			)
		} else if (availableStock < localQuantity.value) {
			hasStock.value = false
			showWarning(
				__('Only {0} units of "{1}" available in "{2}". Current quantity: {3}', [
					availableStock,
					localItem.value.item_name,
					localWarehouse.value,
					localQuantity.value,
				]),
			)
		} else {
			hasStock.value = true
			showSuccess(
				__("{0} units available in \"{1}\"", [availableStock, localWarehouse.value]),
			)
		}
	} catch (error) {
		console.error("Error checking warehouse stock:", error)
		hasStock.value = true
	} finally {
		isCheckingStock.value = false
	}
}

function handleDiscountTypeChange() {
	discountValue.value = 0
	calculateTotals()
}

function calculateDiscount() {
	if (discountValue.value !== null && discountValue.value !== undefined && !isNaN(discountValue.value)) {
		discountValue.value = roundCurrency(discountValue.value)
	}

	if (discountType.value === "percentage") {
		if (discountValue.value > 100) {
			discountValue.value = 100
		}
		calculatedDiscount.value = roundCurrency((calculatedSubtotal.value * discountValue.value) / 100)
	} else {
		if (discountValue.value > calculatedSubtotal.value) {
			discountValue.value = roundCurrency(calculatedSubtotal.value)
		}
		calculatedDiscount.value = roundCurrency(discountValue.value)
	}
	calculatedTotal.value = roundCurrency(calculatedSubtotal.value - calculatedDiscount.value)
}

function calculateTotals() {
	calculatedSubtotal.value = localRate.value * localQuantity.value
	calculateDiscount()
}

function removeSerial(serialNo) {
	const index = localSerials.value.indexOf(serialNo)
	if (index > -1) {
		localSerials.value.splice(index, 1)
		removedSerials.value.push(serialNo)
		localQuantity.value = localSerials.value.length
		calculateTotals()
	}
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}

function updateItem() {
	const isRateManuallyEdited = localRate.value !== originalPriceListRate.value

	if (settingsStore.allowUserToEditRate && isRateManuallyEdited) {
		if (localRate.value <= 0) {
			showError(__('Rate must be greater than zero'))
			return
		}

		const maxDiscount = settingsStore.maxDiscountAllowed
		if (maxDiscount > 0 && localRate.value < originalPriceListRate.value) {
			const discountPercent = ((originalPriceListRate.value - localRate.value) / originalPriceListRate.value) * 100
			const roundedDiscount = Math.round(discountPercent * 100) / 100

			if (roundedDiscount > maxDiscount) {
				showError(
					__('Rate reduction of {0}% exceeds maximum allowed discount of {1}%', [
						roundedDiscount.toFixed(2),
						maxDiscount,
					]),
				)
				return
			}
		}
	}

	const applied = uomPolicyAdapter.applySelectedUom(localItem.value, localUom.value)
	if (!applied.ok) {
		showError(
			__('UOM "{0}" is not allowed for item "{1}".', [
				localUom.value,
				localItem.value.item_name || localItem.value.item_code,
			]),
		)
		return
	}

	const updatedItem = {
		...applied.item,
		quantity: localQuantity.value,
		uom: applied.item.uom,
		rate: localRate.value,
		price_list_rate: originalPriceListRate.value,
		warehouse: localWarehouse.value,
		discount_percentage:
			discountType.value === "percentage" ? discountValue.value : 0,
		discount_amount:
			discountType.value === "amount" ? discountValue.value : 0,
		is_rate_manually_edited: isRateManuallyEdited ? 1 : 0,
		original_rate: isRateManuallyEdited ? originalPriceListRate.value : null,
	}

	if (localItem.value.has_serial_no) {
		updatedItem.serial_no = localSerials.value.join("\n")
		updatedItem.quantity = localSerials.value.length

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

.z-dialog-overlay {
	z-index: var(--z-dialog-overlay, 400);
}

.z-dialog-content {
	z-index: var(--z-dialog-content, 500);
}
</style>