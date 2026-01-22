<template>
	<Dialog v-model="isOpen" :options="{ title: dialogTitle, size: 'md' }">
		<template #body-content>
			<div class="py-4">
				<div v-if="item" class="mb-4">
					<div class="flex items-center gap-3 mb-3">
						<div class="w-12 h-12 bg-gray-100 rounded flex items-center justify-center overflow-hidden flex-shrink-0">
							<img v-if="item.image" :src="item.image" loading="lazy" :alt="item.item_name" class="w-full h-full object-cover" />
							<svg v-else class="h-6 w-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
							</svg>
						</div>
						<div class="flex-1">
							<h3 class="text-sm font-semibold text-gray-900">{{ item.item_name }}</h3>
							<p class="text-xs text-gray-500">{{ item.item_code }}</p>
						</div>
					</div>
					<p class="text-xs text-gray-600 mb-3 text-start">{{ dialogDescription }}</p>
				</div>

				<!-- Loading State -->
				<div v-if="loading" class="flex items-center justify-center py-8">
					<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
					<p class="ms-3 text-sm text-gray-500">{{ __('Loading options...') }}</p>
				</div>

				<!-- Variant Options with Attribute Selection -->
				<div v-else-if="mode === 'variant' && options.length > 0" class="flex flex-col gap-4">
					<!-- Display item image and info - show variant image when selected, otherwise template image -->
					<div class="flex items-center justify-center mb-4">
						<img
							v-if="matchedVariant?.data?.image || item?.image"
							:src="matchedVariant?.data?.image || item.image"
							loading="lazy"
							:alt="matchedVariant?.label || item.item_name"
							class="w-32 h-32 object-contain rounded-lg transition-opacity duration-300"
						/>
					</div>

					<!-- Group variants by attributes -->
					<div v-for="(values, attrName) in variantAttributesMap" :key="attrName" class="flex flex-col gap-2">
						<label class="text-sm font-semibold text-gray-900 text-start block">{{ attrName }}</label>
						<div class="flex flex-wrap gap-2">
							<button
								v-for="value in values"
								:key="value"
								@click="selectAttribute(attrName, value)"
								:class="[
									'px-4 py-2 rounded-lg border-2 text-sm font-medium transition-all',
									selectedAttributes[attrName] === value
										? 'border-blue-500 bg-blue-500 text-white'
										: 'border-gray-300 bg-white text-gray-700 hover:border-blue-300'
								]"
							>
								{{ value }}
							</button>
						</div>
					</div>

					<!-- Show selected variant info -->
					<div v-if="matchedVariant" class="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg">
						<div class="flex items-center justify-between">
							<div>
								<p class="text-sm font-semibold text-gray-900">{{ matchedVariant.label }}</p>
								<p class="text-xs text-gray-500">{{ matchedVariant.description }}</p>
							</div>
							<div class="text-end">
								<p class="text-sm font-bold text-blue-600">{{ formatCurrency(matchedVariant.rate || 0) }}</p>
								<p class="text-xs" :class="(matchedVariant.stock ?? matchedVariant.data?.actual_qty ?? 0) > 0 ? 'text-green-600' : 'text-red-600'">
									 {{ __('Stock: {0}', [(matchedVariant.stock ?? matchedVariant.data?.actual_qty ?? 0)]) }}
								</p>
							</div>
						</div>
					</div>

					<!-- Warning if combination not found -->
					<div v-else-if="allAttributesSelected" class="mt-4 p-3 bg-orange-50 border border-orange-200 rounded-lg">
						<p class="text-xs text-orange-700">{{ __('This combination is not available') }}</p>
					</div>
				</div>

				<!-- UOM Options (Fast Cashier UI) -->
				<div v-else-if="mode === 'uom' && options.length > 0" class="flex flex-col gap-4">
					<!-- UOM Selection Buttons -->
					<div>
						<label class="block text-sm font-medium text-gray-700 mb-2 text-start">{{ __('Unit of Measure') }}</label>
						<div class="grid gap-2" :class="options.length <= 2 ? 'grid-cols-2' : 'grid-cols-3'">
							<button
								v-for="(option, index) in options"
								:key="index"
								@click="selectOption(option)"
								:class="[
									'px-4 py-3 rounded-xl font-bold text-base transition-all touch-manipulation flex flex-col items-center justify-center min-h-[60px]',
									selectedOption === option
										? 'bg-blue-600 text-white shadow-lg ring-2 ring-blue-300'
										: 'bg-gray-100 text-gray-700 hover:bg-gray-200 active:bg-gray-300'
								]"
							>
								<span>{{ option.label }}</span>
								<span :class="['text-xs mt-0.5', selectedOption === option ? 'text-blue-100' : 'text-gray-500']">
									{{ formatCurrency(option.rate || 0) }}
								</span>
							</button>
						</div>
					</div>

					<!-- Quantity Control -->
					<div>
						<label class="block text-sm font-medium text-gray-700 mb-2 text-start">{{ __('Quantity') }}</label>
						<div class="w-full h-10 border border-gray-300 rounded-lg bg-white flex items-center overflow-hidden">
							<button
								type="button"
								@click="decrementQuantity"
								class="w-[40px] h-[40px] min-w-[40px] bg-gray-100 hover:bg-gray-200 active:bg-gray-300 text-gray-700 font-bold text-lg transition-colors flex items-center justify-center border-e border-gray-300 touch-manipulation"
								style="flex: 0 0 40px;"
							>
								−
							</button>
							<div class="flex-1 h-full flex items-center justify-center px-3">
								<input
									v-model.number="quantity"
									type="number"
									min="1"
									step="1"
									inputmode="numeric"
									class="w-full text-center border-0 text-sm font-semibold focus:outline-none focus:ring-0 bg-transparent [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
									@blur="validateQuantity"
									@keydown.enter="confirm"
								/>
							</div>
							<button
								type="button"
								@click="incrementQuantity"
								class="w-[40px] h-[40px] min-w-[40px] bg-gray-100 hover:bg-gray-200 active:bg-gray-300 text-gray-700 font-bold text-lg transition-colors flex items-center justify-center border-s border-gray-300 touch-manipulation"
								style="flex: 0 0 40px;"
							>
								+
							</button>
						</div>

						<!-- Quick Quantity Buttons -->
						<div class="flex gap-2 mt-3">
							<button
								v-for="qty in [1, 5, 10, 20]"
								:key="qty"
								@click="quantity = qty"
								:class="[
									'flex-1 py-3 rounded-xl text-sm font-bold transition-all touch-manipulation',
									quantity === qty
										? 'bg-blue-600 text-white shadow-md'
										: 'bg-gray-100 text-gray-600 hover:bg-gray-200 active:bg-gray-300'
								]"
							>
								{{ qty }}
							</button>
						</div>
					</div>

					<!-- Price Summary -->
					<div class="bg-blue-50 rounded-xl p-4 flex items-center justify-between">
						<div>
							<p class="text-sm text-gray-600">{{ __('Total') }}</p>
							<p class="text-xs text-gray-500">{{ quantity }} × {{ formatCurrency(selectedOption?.rate || options[0]?.rate || 0) }}</p>
						</div>
						<p class="text-2xl font-bold text-blue-600">
							{{ formatCurrency((selectedOption?.rate || options[0]?.rate || 0) * quantity) }}
						</p>
					</div>

					<!-- Stock Warning -->
					<p v-if="stockWarning" class="text-xs text-orange-600 flex items-center justify-center gap-1 bg-orange-50 rounded-lg p-2">
						<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
						</svg>
						{{ stockWarning }}
					</p>
				</div>

				<!-- No Options -->
				<div v-else class="text-center py-8">
					<div class="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-orange-100 mb-3">
						<svg class="h-6 w-6 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
						</svg>
					</div>
					<p class="text-sm font-medium text-gray-900">
						{{ mode === 'variant'
							? __('No Variants Available')
							: __('No Options Available')
						}}
					</p>
					<p v-if="mode === 'variant'" class="text-xs text-gray-500 mt-2">
						<TranslatedHTML 
							:inner="__('This item template &lt;strong&gt;{0}&lt;strong&gt; has no variants created yet.', [item?.item_name])"
						/>
					</p>
					<p v-else class="text-xs text-gray-500 mt-2">
						{{ __('No additional units of measurement configured for this item.') }}
					</p>
					<div v-if="mode === 'variant'" class="mt-4">
						<p class="text-xs text-gray-600 mb-2">{{ __('To create variants:') }}</p>
						<ol class="text-xs text-gray-600 text-start max-w-xs mx-auto flex flex-col gap-1">
							<TranslatedHTML 
								:tag="'li'"
								:inner="__('1. Go to &lt;strong&gt;Item Master&lt;strong&gt; → &lt;strong&gt;{0}&lt;strong&gt;', [item?.item_code])"
							/>
							<TranslatedHTML
								:tag="'li'"
								:inner="__('2. Click &lt;strong&gt;&quot;Make Variants&quot;&lt;strong&gt; button')"
							/>
							<li>{{ __('3. Select attribute combinations') }}</li>
							<TranslatedHTML
								:tag="'li'"
								:inner="__('4. Click &lt;strong&gt;&quot;Create&quot;&lt;strong&gt;')"
							/>
						</ol>
					</div>
				</div>
			</div>
		</template>

		<template #actions>
			<div class="flex gap-2 w-full">
				<Button class="flex-1" variant="subtle" @click="cancel">
					{{ __('Cancel') }}
				</Button>
				<Button class="flex-1" variant="solid" theme="blue" @click="confirm" :disabled="!selectedOption">
					{{ confirmButtonText }}
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { Button, Dialog } from "frappe-ui"
import { createResource } from "frappe-ui"
import { computed, ref, watch } from "vue"
import TranslatedHTML from "../common/TranslatedHTML.vue"
import { offlineState } from "@/utils/offline/offlineState"
import { getCachedVariants, cacheItems } from "@/utils/offline/items"

const props = defineProps({
	modelValue: Boolean,
	item: Object,
	mode: {
		type: String, // 'uom' or 'variant'
		default: "uom",
	},
	posProfile: String,
	currency: {
		type: String,
		default: "USD",
	},
})

const emit = defineEmits(["update:modelValue", "option-selected"])

const isOpen = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
})

const loading = ref(false)
const options = ref([])
const selectedOption = ref(null)
const quantity = ref(1)
const selectedAttributes = ref({}) // For variant attribute selection

// Computed properties for dialog customization
const dialogTitle = computed(() => {
	return props.mode === "variant"
		? __("Select Item Variant")
		: __("Select Unit of Measure")
})

const dialogDescription = computed(() => {
	return props.mode === "variant"
		? __("Choose a variant of this item:")
		: __("Select the unit of measure for this item:")
})

const confirmButtonText = computed(() => {
	return props.mode === "variant" ? __("Add to Cart") : __("Add to Cart")
})

// Computed: Stock warning when quantity exceeds available stock
const stockWarning = computed(() => {
	if (props.mode !== "uom" || !selectedOption.value) return null

	const availableStock = selectedOption.value.stock_qty ?? selectedOption.value.actual_qty ?? null
	if (availableStock === null) return null

	if (quantity.value > availableStock) {
		return __("Requested quantity ({0}) exceeds available stock ({1})", [quantity.value, Math.floor(availableStock)])
	}
	return null
})

/**
 * Validates quantity input ensuring it's a valid positive integer
 */
function validateQuantity() {
	// Handle invalid, negative, or decimal values
	if (!quantity.value || isNaN(quantity.value) || quantity.value < 1) {
		quantity.value = 1
	} else {
		// Round to nearest integer for UOM quantities
		quantity.value = Math.max(1, Math.round(quantity.value))
	}
}

// Quantity counter functions
function incrementQuantity() {
	quantity.value = Math.max(1, quantity.value + 1)
}

function decrementQuantity() {
	if (quantity.value > 1) {
		quantity.value = quantity.value - 1
	}
}

// Computed: Build a map of all available attribute values
const variantAttributesMap = computed(() => {
	if (props.mode !== "variant" || options.value.length === 0) return {}

	const attrMap = {}
	options.value.forEach((option) => {
		Object.entries(option.attributes || {}).forEach(([key, value]) => {
			if (!attrMap[key]) {
				attrMap[key] = new Set()
			}
			attrMap[key].add(value)
		})
	})

	// Convert Sets to sorted Arrays
	const result = {}
	Object.keys(attrMap).forEach((key) => {
		result[key] = Array.from(attrMap[key]).sort()
	})

	return result
})

// Computed: Check if all attributes are selected
const allAttributesSelected = computed(() => {
	const attrKeys = Object.keys(variantAttributesMap.value)
	return (
		attrKeys.length > 0 &&
		attrKeys.every((key) => selectedAttributes.value[key])
	)
})

// Computed: Find variant that matches selected attributes
const matchedVariant = computed(() => {
	if (!allAttributesSelected.value) return null

	return options.value.find((option) => {
		return Object.entries(selectedAttributes.value).every(([key, value]) => {
			return option.attributes[key] === value
		})
	})
})

/**
 * Transform raw variant data into option format for the UI
 */
function mapVariantsToOptions(variants) {
	return variants.map((v) => ({
		type: "variant",
		item_code: v.item_code,
		label: v.item_name,
		description: v.item_code,
		attributes: v.attributes || {},
		rate: v.rate || v.price_list_rate || 0,
		priceLabel: __('per {0}', [v.stock_uom]),
		stock: v.actual_qty ?? 0,
		data: v,
	}))
}

/**
 * Load variants from IndexedDB cache (for offline mode or API fallback)
 */
async function loadVariantsFromCache() {
	try {
		const cachedVariants = await getCachedVariants(props.item?.item_code)
		options.value = cachedVariants?.length > 0 ? mapVariantsToOptions(cachedVariants) : []
	} catch (error) {
		console.error("Error loading variants from cache:", error)
		options.value = []
	} finally {
		loading.value = false
	}
}

// Resource for fetching variants from API
const variantsResource = createResource({
	url: "pos_next.api.items.get_item_variants",
	makeParams() {
		return {
			template_item: props.item?.item_code,
			pos_profile: props.posProfile,
		}
	},
	auto: false,
	async onSuccess(data) {
		const variants = data?.message || data || []
		options.value = mapVariantsToOptions(variants)
		loading.value = false

		// Cache variants for offline use
		if (variants.length > 0) {
			cacheItems(variants).catch((err) => console.error("Error caching variants:", err))
		}
	},
	async onError(error) {
		console.error("Error loading variants:", error)
		// Try cache as fallback (user might have just gone offline)
		await loadVariantsFromCache()
	},
})

// Load options when dialog opens
watch(
	() => props.modelValue,
	(isOpen) => {
		if (isOpen && props.item) {
			loadOptions()
		}
	},
)

// Watch mode and item changes to reload options
watch([() => props.mode, () => props.item], ([, newItem]) => {
	if (props.modelValue && newItem) {
		loadOptions()
	}
})

/**
 * Load options based on mode (variant or UOM)
 */
async function loadOptions() {
	selectedOption.value = null
	quantity.value = props.item.resolved_qty || 1
	selectedAttributes.value = {} // Reset attribute selection

	if (props.mode === "variant") {
		loading.value = true

		if (offlineState.isOffline) {
			await loadVariantsFromCache()
		} else {
			variantsResource.reload()
		}
	} else {
		// Load UOM options
		options.value = buildUomOptions()
		if (options.value.length > 0) {
			// Check if item has a single barcode UOM to auto-select
			const barcodeUoms = props.item?.barcode_uoms
				? props.item.barcode_uoms.split(",").filter(Boolean)
				: []

			if (barcodeUoms.length === 1) {
				// Find and select the matching UOM option
				const uom = props.item.resolved_uom || barcodeUoms[0]
				const matchingOption = options.value.find((opt) => opt.uom === uom)
				selectedOption.value = matchingOption || options.value[0]
			} else {
				// Default to first option (stock UOM)
				selectedOption.value = options.value[0]
			}
		}
		loading.value = false
	}
}

// Watch matched variant and auto-select it
watch(matchedVariant, (variant) => {
	if (variant) {
		selectedOption.value = variant
	} else {
		selectedOption.value = null
	}
})

function buildUomOptions() {
	if (!props.item) return []

	const uomOptions = []

	// Stock UOM option
	uomOptions.push({
		type: "uom",
		uom: props.item.stock_uom,
		conversion_factor: 1,
		label: props.item.stock_uom,
		description: __("Stock unit"),
		rate: getUomPrice(props.item.stock_uom, 1),
		priceLabel: __('per {0}', [props.item.stock_uom]),
	})

	// Additional UOMs
	if (props.item.item_uoms && props.item.item_uoms.length > 0) {
		props.item.item_uoms.forEach((uomData) => {
			uomOptions.push({
				type: "uom",
				uom: uomData.uom,
				conversion_factor: uomData.conversion_factor,
				label: uomData.uom,
				description: __('1 {0} = {1} {2}', [uomData.uom, uomData.conversion_factor, props.item.stock_uom]),
				rate: getUomPrice(uomData.uom, uomData.conversion_factor),
				priceLabel: __('per {0}', [uomData.uom]),
			})
		})
	}

	return uomOptions
}

function getUomPrice(uom, conversionFactor) {
	if (!props.item) return 0

	// Check if we have UOM-specific prices
	if (props.item.uom_prices && props.item.uom_prices[uom]) {
		return props.item.uom_prices[uom]
	}

	// Calculate price based on conversion factor
	// If 1 Gram = 0.001 Kg, then price per Gram = price per Kg * 0.001
	const baseRate = props.item.rate || 0
	return baseRate * conversionFactor
}

function selectAttribute(attributeName, value) {
	selectedAttributes.value[attributeName] = value
	// Force reactivity
	selectedAttributes.value = { ...selectedAttributes.value }
}

function selectOption(option) {
	selectedOption.value = option
}

function confirm() {
	if (selectedOption.value) {
		// Emit first, let parent decide if dialog should close
		// Parent can keep dialog open by switching mode (variant → UOM)
		const option = { ...selectedOption.value }
		if (props.mode === "uom") {
			option.quantity = quantity.value
		}
		emit("option-selected", option)
	}
}

function cancel() {
	selectedOption.value = null
	selectedAttributes.value = {}
	isOpen.value = false
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}
</script>
