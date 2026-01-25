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
														{{ formatCurrency(localItem.price_list_rate || localItem.rate) }} / {{ localItem.stock_uom || __('Nos', null, 'UOM') }}
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
																readonly
																class="w-full h-7 border border-gray-300 rounded-lg ps-12 pe-3 text-sm font-semibold bg-gray-50 cursor-not-allowed"
															/>
														</div>
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
                            <!-- For resolved barcode items, UOM is read-only -->
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
													<!-- Discount Type -->
													<div>
														<label class="block text-xs text-gray-600 mb-1 text-start">{{ __('Discount Type') }}</label>
														<SelectInput v-model="discountType" :options="discountTypeOptions" @change="handleDiscountTypeChange" />
													</div>
													<!-- Discount Value -->
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
import { useToast } from "@/composables/useToast"
import { usePOSSettingsStore } from "@/stores/posSettings"
import { useSerialNumberStore } from "@/stores/serialNumber"
import { getItemStock } from "@/utils/stockValidator"
import { formatCurrency as formatCurrencyUtil, getCurrencySymbol, round2 } from "@/utils/currency"
import { Button, FeatherIcon } from "frappe-ui"
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
const localSerials = ref([]) // List of serial numbers for this item
const removedSerials = ref([]) // Track serials removed during this edit session
const originalSerials = ref([]) // Original serials when dialog opened

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

// Options for SelectInput components
const uomOptions = computed(() => {
	if (!localItem.value) return []
	const options = [{ value: localItem.value.stock_uom, label: localItem.value.stock_uom }]
	if (availableUoms.value.length > 0) {
		availableUoms.value.forEach(uomData => {
			options.push({ value: uomData.uom, label: uomData.uom })
		})
	}
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

const discountTypeOptions = computed(() => [
	{ value: 'percentage', label: __('Percentage (%)') },
	{ value: 'amount', label: __('Amount') }
])

// Initialize local state when item changes
watch(
	() => props.item,
	(newItem) => {
		if (newItem) {
			localItem.value = { ...newItem }
			localQuantity.value = newItem.quantity || 1
			localUom.value = newItem.uom || newItem.stock_uom || __("Nos")
			localRate.value = newItem.rate || 0
			localWarehouse.value =
				newItem.warehouse || props.warehouses[0]?.name || ""

			// Initialize serial numbers
			if (newItem.has_serial_no && newItem.serial_no) {
				const serials = newItem.serial_no.split('\n').filter(s => s.trim())
				localSerials.value = [...serials]
				originalSerials.value = [...serials] // Keep original for cancel
				removedSerials.value = [] // Reset removed serials tracker
				// For serial items, quantity must match serial count
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

			// Reset stock check state
			hasStock.value = true
			isCheckingStock.value = false

			calculateTotals()
		}
	},
	{ immediate: true },
)

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

function handleUomChange() {
	// When UOM changes, we need to fetch new rate from server
	// For now, we'll just recalculate with current rate
	calculateTotals()
}

async function handleWarehouseChange() {
	if (!localItem.value || !localWarehouse.value) return

	isCheckingStock.value = true
	try {
		// Check stock availability in the new warehouse
		const availableStock = await getItemStock(
			localItem.value.item_code,
			localWarehouse.value,
		)

		if (availableStock === 0) {
			hasStock.value = false
			showError(
				__('"{0}" is not available in warehouse "{1}". Please select another warehouse.',
				[localItem.value.item_name, localWarehouse.value])
			)
		} else if (availableStock < localQuantity.value) {
			hasStock.value = false
			showWarning(
				__('Only {0} units of "{1}" available in "{2}". Current quantity: {3}', [
					availableStock,
					localItem.value.item_name,
					localWarehouse.value,
					localQuantity.value
				])
			)
		} else {
			hasStock.value = true
			showSuccess(
				__('{0} units available in "{1}"', [availableStock, localWarehouse.value])
			)
		}
	} catch (error) {
		console.error("Error checking warehouse stock:", error)
		hasStock.value = true // Allow update if stock check fails
	} finally {
		isCheckingStock.value = false
	}
}

function handleDiscountTypeChange() {
	// Reset discount value when type changes
	discountValue.value = 0
	calculateTotals()
}

function calculateDiscount() {
	// Round to 2 decimal places to prevent floating point precision issues (e.g., 10.000000000000002)
	if (discountValue.value !== null && discountValue.value !== undefined && !isNaN(discountValue.value)) {
		discountValue.value = round2(discountValue.value)
	}

	if (discountType.value === "percentage") {
		// Ensure percentage doesn't exceed 100
		if (discountValue.value > 100) {
			discountValue.value = 100
		}
		calculatedDiscount.value = round2((calculatedSubtotal.value * discountValue.value) / 100)
	} else {
		// Ensure amount doesn't exceed subtotal
		if (discountValue.value > calculatedSubtotal.value) {
			discountValue.value = round2(calculatedSubtotal.value)
		}
		calculatedDiscount.value = round2(discountValue.value)
	}
	calculatedTotal.value = round2(calculatedSubtotal.value - calculatedDiscount.value)
}

function calculateTotals() {
	calculatedSubtotal.value = localRate.value * localQuantity.value
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

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}

function updateItem() {
	const updatedItem = {
		...localItem.value,
		quantity: localQuantity.value,
		uom: localUom.value,
		rate: localRate.value,
		warehouse: localWarehouse.value,
		discount_percentage:
			discountType.value === "percentage" ? discountValue.value : 0,
		discount_amount:
			discountType.value === "amount" ? discountValue.value : 0,
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
